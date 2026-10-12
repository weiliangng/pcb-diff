"""Comparison pipeline and stable output schema. Rendering uses physical coordinates."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import html
import io
import json
import math
import re
import shutil
import tempfile
import uuid
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
from scipy import ndimage as ndi
from gerbonara import GerberFile
from resvg_py import svg_to_bytes
from . import __version__
from .layers import extract, pair_layers

DEFAULT_PALETTE = {'background':'#0f1621','unchanged':'#707c8f','added':'#23e89a','removed':'#ff4a66','text':'#e6ecf5'}

@contextmanager
def output_stage(parent):
    # Normal mkdir inherits the destination ACL on Windows. tempfile.mkdtemp's
    # private ACL must not be carried into a user-facing report by renaming it.
    parent = Path(parent).resolve()
    stage = parent / ('.pcb-diff-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        yield stage
    finally:
        if stage.exists():
            resolved = stage.resolve()
            if resolved.parent != parent or not resolved.name.startswith('.pcb-diff-'):
                raise RuntimeError('Refusing to remove an unexpected staging path.')
            shutil.rmtree(resolved)

@dataclass
class Options:
    dpmm: float = 50
    tolerance_mm: float = .02
    threshold: int = 128
    scope: str = 'copper'
    missing: str = 'error'
    margin_mm: float = .5
    region_gap_mm: float = .35
    crop_padding_mm: float = .35
    max_crops: int = 12
    overview_columns: int = 2
    preview_width: int = 1100
    max_megapixels: float = 60
    new_offset_mm: tuple = (0,0)
    palette: dict = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    layer_map: str | None = None
    archive_tool: str | None = None

def validate(options):
    for name in ('dpmm','max_megapixels'):
        value = getattr(options,name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name + ' must be positive and finite.')
    for name in ('tolerance_mm','margin_mm','region_gap_mm','crop_padding_mm'):
        value = getattr(options,name)
        if not math.isfinite(value) or value < 0:
            raise ValueError(name + ' must be nonnegative and finite.')
    if not 1 <= options.threshold <= 255:
        raise ValueError('Threshold must be between 1 and 255.')
    if options.max_crops < 0 or options.overview_columns < 1 or options.preview_width < 200:
        raise ValueError('Crops must be nonnegative, columns positive and preview width at least 200.')
    if len(options.new_offset_mm)!=2 or not all(math.isfinite(x) for x in options.new_offset_mm):
        raise ValueError('Offset must contain two finite millimetre values.')
    if options.scope not in ('copper','all') or options.missing not in ('error','skip','empty'):
        raise ValueError('Invalid scope or missing-layer policy.')
    if set(options.palette) != set(DEFAULT_PALETTE):
        raise ValueError('Palette keys must be: ' + ', '.join(DEFAULT_PALETTE))
    for color in options.palette.values():
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            raise ValueError('Palette colors must be #RRGGBB values.')

def render(layer, bounds, width, height, threshold=128):
    if layer is None:
        return np.zeros((height,width), dtype=bool)
    svg = str(layer.to_svg(force_bounds=bounds, fg='white', bg='black'))
    svg, replaced = re.subn(r'(<svg\s+)width="[^"]+" height="[^"]+"', rf'\g<1>width="{width}px" height="{height}px"', svg, count=1)
    if replaced != 1:
        raise ValueError('Unexpected renderer SVG root; cannot enforce the shared canvas.')
    png = svg_to_bytes(svg_string=svg, dpi=96, background='black', skip_system_fonts=True)
    image = Image.open(io.BytesIO(png)).convert('L')
    if image.size != (width,height):
        raise ValueError(f'Unexpected canvas size {image.size}; expected {(width,height)}.')
    return np.asarray(image) >= threshold

def tolerant_delta(old, new, radius_pixels):
    """Euclidean distance between pixel centres; exclude nearby edge differences."""
    if radius_pixels <= 0:
        return new & ~old, old & ~new
    if old.any():
        distance = ndi.distance_transform_edt(~old)
        added = new & (distance > radius_pixels)
        del distance
    else:
        added = new.copy()
    if new.any():
        distance = ndi.distance_transform_edt(~new)
        removed = old & (distance > radius_pixels)
        del distance
    else:
        removed = old.copy()
    return added, removed

def color_image(old,new,added,removed,palette):
    colors = {k:ImageColor.getrgb(v) for k,v in palette.items()}
    image = np.full((*old.shape,3), colors['background'], dtype=np.uint8)
    image[old|new] = colors['unchanged']
    image[added] = colors['added']
    image[removed] = colors['removed']
    return Image.fromarray(image)

def find_regions(added,removed,bounds,options):
    mask = added | removed
    radius = round(options.region_gap_mm*options.dpmm)
    nearby = ndi.maximum_filter(mask,size=2*radius+1) if radius else mask
    labels,_ = ndi.label(nearby,structure=np.ones((3,3)))
    regions = []
    for index,box in enumerate(ndi.find_objects(labels),1):
        if box is None: continue
        ys,xs = box
        selected = labels[box] == index
        ap = int(np.count_nonzero(added[box] & selected))
        rp = int(np.count_nonzero(removed[box] & selected))
        if ap+rp == 0: continue
        regions.append({'box_pixels':[xs.start,ys.start,xs.stop,ys.stop],
            'box_mm':[bounds[0][0]+xs.start/options.dpmm,bounds[1][1]-ys.stop/options.dpmm,bounds[0][0]+xs.stop/options.dpmm,bounds[1][1]-ys.start/options.dpmm],
            'added_mm2':ap/options.dpmm**2,'removed_mm2':rp/options.dpmm**2})
    return sorted(regions,key=lambda r:r['added_mm2']+r['removed_mm2'],reverse=True)

def font(size):
    # Prefer a discoverable font, then Pillow's embedded fallback. No OS path is required.
    try: return ImageFont.truetype('DejaVuSans.ttf',size)
    except OSError: return ImageFont.load_default(size=size)

def fitted_text(draw, xy, text, max_width, chosen_font, fill):
    while draw.textlength(text,font=chosen_font) > max_width and len(text)>1:
        text = text[:-2] + '…'
    draw.text(xy,text,font=chosen_font,fill=fill)

def save_overview(previews, rows, destination, options, tolerant):
    columns = min(options.overview_columns,len(rows))
    tile_width = options.preview_width + 40
    image_height = max(im.height for im in previews)
    tile_height = image_height + 100
    legend_labels = [('Added','added'),('Removed','removed'),('Unchanged / context','unchanged')]
    available = columns*tile_width
    legend_rows,x = 1,20
    for label,_ in legend_labels:
        length = round(ImageDraw.Draw(Image.new('RGB',(1,1))).textlength(label,font=font(22)))+58
        if x+length > available-20 and x>20:
            legend_rows += 1
            x = 20
        x += length
    header_height = 55+32*legend_rows
    sheet = Image.new('RGB',(available,math.ceil(len(rows)/columns)*tile_height+header_height),options.palette['background'])
    draw = ImageDraw.Draw(sheet)
    title_font, chosen_font = font(22),font(24)
    mode = f'Edge-tolerant ({options.tolerance_mm:g} mm)' if tolerant else 'Exact binary subtraction'
    fitted_text(draw,(20,12),mode+f' · {1000/options.dpmm:g} µm/pixel source renders',sheet.width-40,title_font,options.palette['text'])
    x,y = 20,44
    for label,key in legend_labels:
        length = round(draw.textlength(label,font=title_font))+58
        if x+length > available-20 and x>20:
            x,y = 20,y+32
        draw.rectangle((x,y+5,x+16,y+21),fill=options.palette[key])
        fitted_text(draw,(x+24,y),label,available-x-44,title_font,options.palette['text'])
        x += length
    prefix = 'tolerant' if tolerant else 'exact'
    for i,(image,row) in enumerate(zip(previews,rows)):
        x,y = (i%columns)*tile_width+20,(i//columns)*tile_height+header_height
        fitted_text(draw,(x,y),row['name'],tile_width-40,chosen_font,options.palette['text'])
        fitted_text(draw,(x,y+34),f'+{row[prefix+"_added_mm2"]:.3f} / −{row[prefix+"_removed_mm2"]:.3f} mm²',tile_width-40,title_font,options.palette['text'])
        sheet.paste(image,(x,y+80))
    sheet.save(destination)

def write_report(report,folder):
    options = report['options']
    palette = options['palette']
    cards = []
    for row in report['layers']:
        slug = row['key']
        crops = ''.join(f'<figure><figcaption>Region {i}</figcaption><img loading="lazy" src="{slug}-region-{i:02}.png" alt="Changed region {i}"></figure>' for i in range(1,row['exported_crops']+1))
        cards.append(f'<section id="{slug}"><h2>{html.escape(row["name"])}</h2><p>Exact: +{row["exact_added_mm2"]:.3f} / −{row["exact_removed_mm2"]:.3f} mm². Beyond tolerance: +{row["tolerant_added_mm2"]:.3f} / −{row["tolerant_removed_mm2"]:.3f} mm².</p><div class="links">' + ''.join(f'<a href="{slug}-{suffix}.png">{label}</a>' for suffix,label in [('old','Older'),('new','Newer'),('diff-exact','Exact difference'),('diff-tolerant','Edge-tolerant difference')]) + f'</div><img src="{slug}-diff-exact.png" alt="Exact difference for {html.escape(row["name"])}"><details><summary>{len(row["regions"])} change groups; {row["exported_crops"]} crops</summary><div class="crops">{crops}</div></details></section>')
    ignored = ''.join(f'<li>{version}: {html.escape(item["file"])} — {html.escape(item["reason"])}</li>' for version,items in report['ignored'].items() for item in items)
    nav = ''.join(f'<a href="#{r["key"]}">{html.escape(r["name"])}</a>' for r in report['layers'])
    offset = options['new_offset_mm']
    content = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PCB artwork diff</title><style>
body{{font:16px/1.5 system-ui,sans-serif;background:{palette['background']};color:{palette['text']};max-width:1300px;margin:auto;padding:24px}}a{{color:inherit}}nav,.links,.legend{{display:flex;gap:20px;flex-wrap:wrap}}section{{margin:36px 0}}img{{max-width:100%;height:auto}}.crops{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:18px}}figure{{margin:12px 0}}.swatch{{display:inline-block;width:14px;height:14px;margin-right:6px}}summary{{cursor:pointer}}
</style></head><body><h1>PCB artwork diff</h1><p>Older: {html.escape(report['inputs']['old'])}<br>Newer: {html.escape(report['inputs']['new'])}</p><div class="legend">''' + ''.join(f'<span><i class="swatch" style="background:{palette[key]}"></i>{label}</span>' for key,label in [('added','Added'),('removed','Removed'),('unchanged','Unchanged / context')]) + f'''</div><p>Resolution: {options['dpmm']:g} pixels/mm ({1000/options['dpmm']:g} µm/pixel). Coverage threshold: {options['threshold']}/255. Edge tolerance: {options['tolerance_mm']:g} mm, measured between pixel centres using Euclidean distance. Differences below the raster resolution can be missed. Secondary views show excluded fringe changes as gray context.</p><p>Newer artwork offset: ({offset[0]:g}, {offset[1]:g}) mm. All layers are viewed from above without mirroring; no automatic registration. Areas describe rendered artwork; mask and paste layers show their Gerber exposures. Drill files are excluded and holes are not subtracted. This does not compare electrical connectivity.</p><nav>{nav}</nav><p><a href="overview-exact.png">Exact overview</a> · <a href="overview-tolerant.png">Edge-tolerant overview</a> · <a href="results.json">Detailed results</a></p>{''.join(cards)}<details><summary>Excluded files</summary><ul>{ignored or '<li>No recognized layers excluded</li>'}</ul></details></body></html>'''
    (folder/'report.html').write_text(content,encoding='utf-8')

def compare(old_source,new_source,output,options=None,progress=print):
    options = options or Options()
    validate(options)
    output = Path(output).expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be a new or empty directory; choose a different output location.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pcb-diff-') as tmp, output_stage(output.parent) as stage:
        tmp,stage = Path(tmp),Path(stage)
        progress('Reading inputs and matching layers…')
        old_root,old_single = extract(old_source,tmp/'old',options.archive_tool)
        new_root,new_single = extract(new_source,tmp/'new',options.archive_tool)
        pairs,ignored,outlines = pair_layers(old_root,new_root,old_single or new_single,options.scope,options.missing,options.layer_map)
        parsed,boxes = {},[]
        for pair in pairs:
            layers = []
            for version,path in [('old',pair.old),('new',pair.new)]:
                layer = GerberFile.open(path) if path else None
                if layer is not None and version=='new': layer.offset(*options.new_offset_mm)
                if layer is not None:
                    b = layer.bounding_box()
                    if b is not None: boxes.append(b)
                layers.append(layer)
            parsed[pair.key] = layers
        outline_bounds = {}
        for version,path in outlines.items():
            if path:
                layer = GerberFile.open(path)
                if version=='new': layer.offset(*options.new_offset_mm)
                bounds = layer.bounding_box()
                if bounds is not None:
                    outline_bounds[version] = bounds
                    boxes.append(bounds)
        if not boxes:
            raise ValueError('Both inputs have no drawable geometry.')
        lo = tuple(math.floor((min(b[0][i] for b in boxes)-options.margin_mm)*options.dpmm)/options.dpmm for i in (0,1))
        hi = tuple(math.ceil((max(b[1][i] for b in boxes)+options.margin_mm)*options.dpmm)/options.dpmm for i in (0,1))
        bounds = lo,hi
        width,height = [round((hi[i]-lo[i])*options.dpmm) for i in (0,1)]
        if width<1 or height<1: raise ValueError('Canvas is empty. Increase the margin.')
        if width*height > options.max_megapixels*1e6:
            raise ValueError(f'Canvas is {width*height/1e6:.1f} MP, above the {options.max_megapixels:g} MP limit. Lower --dpmm or increase --max-megapixels if memory permits.')
        report = {'schema_version':1,'tool_version':__version__,'created_utc':datetime.now(timezone.utc).isoformat(),
            'inputs':{'old':str(Path(old_source).resolve()),'new':str(Path(new_source).resolve())},'options':asdict(options),
            'canvas_pixels':[width,height],'bounds_mm':bounds,'outline_bounds_mm':outline_bounds,'ignored':ignored,'layers':[]}
        if options.layer_map:
            report['layer_map'] = json.loads(Path(options.layer_map).read_text(encoding='utf-8'))
        exact_previews,tolerant_previews = [],[]
        for index,pair in enumerate(pairs,1):
            progress(f'Comparing {index}/{len(pairs)}: {pair.name}')
            old_layer,new_layer = parsed[pair.key]
            old,new = [render(layer,bounds,width,height,options.threshold) for layer in (old_layer,new_layer)]
            added,removed = new & ~old,old & ~new
            ta,tr = tolerant_delta(old,new,options.tolerance_mm*options.dpmm)
            regions = find_regions(ta,tr,bounds,options)
            exact = color_image(old,new,added,removed,options.palette)
            tolerant = color_image(old,new,ta,tr,options.palette)
            slug = pair.key
            exact.save(stage/f'{slug}-diff-exact.png')
            tolerant.save(stage/f'{slug}-diff-tolerant.png')
            for label,mask in [('old',old),('new',new),('added-mask',added),('removed-mask',removed),('added-tolerant-mask',ta),('removed-tolerant-mask',tr)]:
                Image.fromarray(mask).save(stage/f'{slug}-{label}.png')
            row = {'key':slug,'name':pair.name,'kind':pair.kind,'old_file':str(pair.old.relative_to(old_root)) if pair.old and old_root.is_dir() else pair.old.name if pair.old else None,
                'new_file':str(pair.new.relative_to(new_root)) if pair.new and new_root.is_dir() else pair.new.name if pair.new else None,
                'old_sha256':hashlib.sha256(pair.old.read_bytes()).hexdigest() if pair.old else None,
                'new_sha256':hashlib.sha256(pair.new.read_bytes()).hexdigest() if pair.new else None,
                'old_artwork_mm2':int(old.sum())/options.dpmm**2,'new_artwork_mm2':int(new.sum())/options.dpmm**2,
                'exact_added_mm2':int(added.sum())/options.dpmm**2,'exact_removed_mm2':int(removed.sum())/options.dpmm**2,
                'tolerant_added_mm2':int(ta.sum())/options.dpmm**2,'tolerant_removed_mm2':int(tr.sum())/options.dpmm**2,
                'regions':regions,'exported_crops':min(options.max_crops,len(regions))}
            for i,region in enumerate(regions[:options.max_crops],1):
                x0,y0,x1,y1 = region['box_pixels']
                pad = round(options.crop_padding_mm*options.dpmm)
                exact.crop((max(0,x0-pad),max(0,y0-pad),min(width,x1+pad),min(height,y1+pad))).save(stage/f'{slug}-region-{i:02}.png')
            for image,previews in [(exact,exact_previews),(tolerant,tolerant_previews)]:
                preview = image.copy()
                preview.thumbnail((options.preview_width,round(options.preview_width*height/width)))
                previews.append(preview)
            report['layers'].append(row)
            del old,new,added,removed,ta,tr,exact,tolerant
        progress('Writing overview images and report…')
        save_overview(exact_previews,report['layers'],stage/'overview-exact.png',options,False)
        save_overview(tolerant_previews,report['layers'],stage/'overview-tolerant.png',options,True)
        write_report(report,stage)
        (stage/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        # Publish only after every layer succeeds. Existing outputs are never silently mixed.
        if output.exists(): output.rmdir()
        stage.rename(output)
    progress(f'Finished: {len(report["layers"])} layer(s). {output}')
    return report

"""Input discovery and deterministic layer pairing, separate from rendering."""
from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import subprocess
import zipfile

@dataclass
class Layer:
    key: str
    name: str
    kind: str
    path: Path

@dataclass
class Pair:
    key: str
    name: str
    kind: str
    old: Path | None
    new: Path | None

SUFFIXES = {
    '.gtl': ('copper-top', 'Top copper', 'copper'),
    '.gbl': ('copper-bottom', 'Bottom copper', 'copper'),
    '.cmp': ('copper-top', 'Top copper', 'copper'),
    '.sol': ('copper-bottom', 'Bottom copper', 'copper'),
    '.gto': ('silkscreen-top', 'Top silkscreen', 'silkscreen'),
    '.gbo': ('silkscreen-bottom', 'Bottom silkscreen', 'silkscreen'),
    '.gts': ('mask-top', 'Top solder mask', 'mask'),
    '.gbs': ('mask-bottom', 'Bottom solder mask', 'mask'),
    '.gtp': ('paste-top', 'Top solder paste', 'paste'),
    '.gbp': ('paste-bottom', 'Bottom solder paste', 'paste'),
    '.gko': ('outline', 'Board outline', 'outline'),
    '.gm1': ('outline', 'Board outline', 'outline'),
    '.gdl': ('document', 'Documentation', 'document'),
    '.gdd': ('drill-drawing', 'Drill drawing', 'document'),
}

def gerber_text(path):
    """Read ASCII Gerbers as data. No board-export instructions are executed."""
    return path.read_text(encoding='utf-8-sig', errors='replace')

def is_gerber(text):
    return bool(re.search(r'%FS[LTD]?[AI].*?\*%|%ADD\d+|%MO(?:MM|IN)\*%', text))

def classify(path, text):
    function = re.search(r'%TF\.FileFunction,([^*]+)\*%', text, re.I)
    if function:
        fields = [s.strip().lower() for s in function.group(1).split(',')]
        if fields[0] == 'copper':
            if 'top' in fields:
                return ('copper-top', 'Top copper', 'copper')
            if 'bot' in fields or 'bottom' in fields:
                return ('copper-bottom', 'Bottom copper', 'copper')
            number = next((int(x[1:]) for x in fields if re.fullmatch(r'l\d+', x)), None)
            if number and number >= 2:
                return (f'copper-inner-{number-1}', f'Inner {number-1} copper', 'copper')
        if fields[0] in ('soldermask', 'legend', 'paste'):
            side = 'bottom' if 'bot' in fields or 'bottom' in fields else 'top' if 'top' in fields else None
            if side:
                kind = {'soldermask':'mask', 'legend':'silkscreen', 'paste':'paste'}[fields[0]]
                return (f'{kind}-{side}', f'{side.title()} {kind}', kind)
        if fields[0] == 'profile':
            return ('outline', 'Board outline', 'outline')
    suffix = path.suffix.lower()
    if suffix in SUFFIXES:
        return SUFFIXES[suffix]
    number = re.fullmatch(r'\.g(\d+)', suffix)
    if number:
        n = int(number.group(1))
        if n > 0:
            return (f'copper-inner-{n}', f'Inner {n} copper', 'copper')
    # KiCad filenames and EasyEDA layer comments; use bounded tokens.
    tokens = (path.stem + ' ' + '\n'.join(re.findall(r'G04\s+Layer:\s*([^*]+)', text, re.I))).lower()
    if re.search(r'(?:^|[_.\s-])(?:f[_.-]cu|toplayer|top[_. -]copper)(?:$|[_.\s-])', tokens):
        return ('copper-top', 'Top copper', 'copper')
    if re.search(r'(?:^|[_.\s-])(?:b[_.-]cu|bottomlayer|bottom[_. -]copper)(?:$|[_.\s-])', tokens):
        return ('copper-bottom', 'Bottom copper', 'copper')
    inner = re.search(r'(?:^|[_.\s-])(?:in(\d+)[_.-]cu|innerlayer(\d+))(?:$|[_.\s-])', tokens)
    if inner:
        n = int(inner.group(1) or inner.group(2))
        return (f'copper-inner-{n}', f'Inner {n} copper', 'copper')
    for token, key, name, kind in [
        ('f_mask','mask-top','Top solder mask','mask'), ('b_mask','mask-bottom','Bottom solder mask','mask'),
        ('f_paste','paste-top','Top solder paste','paste'), ('b_paste','paste-bottom','Bottom solder paste','paste'),
        ('f_silkscreen','silkscreen-top','Top silkscreen','silkscreen'), ('b_silkscreen','silkscreen-bottom','Bottom silkscreen','silkscreen'),
        ('edge_cuts','outline','Board outline','outline'), ('boardoutlinelayer','outline','Board outline','outline'),
    ]:
        if re.search(r'(?:^|[_.\s-])' + token + r'(?:$|[_.\s-])', tokens):
            return key, name, kind
    return None

def extract(source, dest, archive_tool=None):
    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    if source.is_dir():
        return source, False
    if zipfile.is_zipfile(source):
        dest.mkdir(parents=True)
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                if not (dest / member.filename).resolve().is_relative_to(dest.resolve()):
                    raise ValueError(f'Unsafe archive path: {member.filename}')
                if member.file_size > 512 * 1024 * 1024:
                    raise ValueError(f'Archive member too large: {member.filename}')
            if sum(x.file_size for x in archive.infolist()) > 2 * 1024**3:
                raise ValueError('Archive expands beyond 2 GB.')
            archive.extractall(dest)
        return dest, False
    with source.open('rb') as f:
        magic = f.read(8)
    if magic.startswith(b'Rar!'):
        tool = archive_tool or shutil.which('7z') or shutil.which('unrar')
        if not tool:
            raise ValueError('Actual RAR files need 7-Zip/UnRAR on PATH or --archive-tool. ZIP files named .rar need no external tool.')
        dest.mkdir(parents=True)
        if 'unrar' in Path(tool).name.lower():
            command = [str(tool), 'x', '-o+', '-idq', str(source), str(dest) + '/']
        else:
            command = [str(tool), 'x', '-y', '-o' + str(dest), str(source)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or '').strip()[-500:]
            raise ValueError(f'Archive extraction failed ({error.returncode}): {detail}') from error
        return dest, False
    if is_gerber(gerber_text(source)):
        return source, True
    raise ValueError(f'Expected a Gerber file, folder, ZIP or RAR archive: {source.name}')

def discover(root):
    found, ignored, unknown = {}, [], []
    paths = [root] if root.is_file() else sorted(root.rglob('*'))
    for path in paths:
        if not path.is_file():
            continue
        # Avoid interpreting unrelated binary assets or large companion files.
        if path.stat().st_size > 512 * 1024 * 1024:
            ignored.append({'file': str(path.relative_to(root)), 'reason':'Over 512 MB discovery limit'})
            continue
        with path.open('rb') as f:
            head = f.read(8192)
        if b'\x00' in head:
            continue
        text = gerber_text(path)
        if not is_gerber(text):
            continue
        matched = classify(path, text)
        if not matched:
            unknown.append(str(path.relative_to(root)))
            continue
        key, name, kind = matched
        if key in found:
            raise ValueError(f'Ambiguous {name}: {found[key].path.name} and {path.name}. Use --layer-map to select the intended files.')
        found[key] = Layer(key, name, kind, path)
    return found, ignored, unknown

def sort_key(key):
    if key == 'copper-top': return (0,0,key)
    inner = re.fullmatch(r'copper-inner-(\d+)',key)
    if inner: return (1,int(inner.group(1)),key)
    if key == 'copper-bottom': return (2,0,key)
    return (3,0,key)

def map_path(root, value):
    if value is None: return None
    p = (root / value).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError(f'Mapped file is missing or outside its input: {value}')
    if not is_gerber(gerber_text(p)):
        raise ValueError(f'Mapped file is not recognized as Gerber artwork: {value}')
    return p

def pair_layers(old_root, new_root, single, scope, missing, layer_map=None):
    if single:
        if not old_root.is_file() or not new_root.is_file():
            raise ValueError('Compare two individual files or two archives/folders; mixing them needs an extracted folder and --layer-map.')
        return [Pair('layer','Layer comparison','artwork',old_root,new_root)], {'old':[], 'new':[]}, {}
    if layer_map:
        data = json.loads(Path(layer_map).read_text(encoding='utf-8'))
        rows = data['layers']
        pairs = []
        for i,row in enumerate(rows,1):
            pairs.append(Pair(f'layer-{i}', row['name'], row.get('kind','artwork'), map_path(old_root,row.get('old')),map_path(new_root,row.get('new'))))
        if not pairs or any(p.old is None and p.new is None for p in pairs):
            raise ValueError('Layer map must include at least one comparison and at least one input per pair.')
        if any(p.old is None or p.new is None for p in pairs) and missing != 'empty':
            raise ValueError('Null layer-map inputs require --missing empty.')
        # A manual map is authoritative and deliberately bypasses auto-discovery.
        return pairs, {'old':[], 'new':[]}, {}
    a, ai, au = discover(old_root)
    b, bi, bu = discover(new_root)
    unknown = {'old':au,'new':bu}
    if au or bu:
        raise ValueError('Gerber layers with unknown roles require --layer-map: ' + json.dumps(unknown))
    filtered = {'old':[{'file':x.path.name,'reason':'Outside selected scope'} for x in a.values() if scope=='copper' and x.kind!='copper'] + ai, 'new':[{'file':x.path.name,'reason':'Outside selected scope'} for x in b.values() if scope=='copper' and x.kind!='copper'] + bi}
    outlines = {'old':a['outline'].path if 'outline' in a else None, 'new':b['outline'].path if 'outline' in b else None}
    a = {k:v for k,v in a.items() if scope=='all' or v.kind=='copper'}
    b = {k:v for k,v in b.items() if scope=='all' or v.kind=='copper'}
    absent = set(a)^set(b)
    if absent and missing=='error':
        raise ValueError('Unpaired layers: ' + ', '.join(sorted(absent)) + '. Use --layer-map, --missing skip or --missing empty.')
    pairs = []
    for key in sorted(set(a)|set(b),key=sort_key):
        if key in absent and missing=='skip':
            version = 'old' if key in a else 'new'
            filtered[version].append({'file':(a.get(key) or b[key]).path.name,'reason':'No counterpart; --missing skip'})
            continue
        info = a.get(key) or b[key]
        pairs.append(Pair(key,info.name,info.kind,a[key].path if key in a else None,b[key].path if key in b else None))
    if not pairs:
        raise ValueError('No layers to compare. Use --scope all or provide --layer-map.')
    return pairs, filtered, outlines

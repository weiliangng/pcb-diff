import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from . import __version__

def main(argv=None):
    parser = argparse.ArgumentParser(prog='pcb-diff',description='Compare two Gerber files, archives or folders and write PNG differences.')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('old',help='Older Gerber file, ZIP/RAR archive or folder')
    parser.add_argument('new',help='Newer Gerber file, ZIP/RAR archive or folder')
    parser.add_argument('-o','--output',default='pcb-diff-'+datetime.now().strftime('%Y%m%d-%H%M%S'),help='New or empty output folder')
    parser.add_argument('--scope',choices=['copper','all'],default='copper',help='Automatically matched layer types; default copper')
    parser.add_argument('--all',action='store_const',const='all',dest='scope',help='Alias for --scope all')
    parser.add_argument('--layer-map',help='JSON file of explicit old/new layer pairs (overrides auto-matching and scope)')
    parser.add_argument('--missing',choices=['error','skip','empty'],default='error',help='Policy for unpaired layers; default error')
    parser.add_argument('--dpmm',type=float,default=50,help='Pixels per mm; default 50 (20 µm/pixel)')
    tolerance = parser.add_mutually_exclusive_group()
    tolerance.add_argument('--tolerance-mm',type=float,default=None,help='Secondary Euclidean edge tolerance in mm; default 0.02')
    tolerance.add_argument('--tolerance-pixels',type=float,help='Alternative tolerance expressed in pixels')
    parser.add_argument('--threshold',type=int,default=128,help='Raster exposure coverage threshold, 1–255; default 128')
    parser.add_argument('--new-offset-mm',type=float,nargs=2,default=(0,0),metavar=('DX','DY'),help='Explicit translation of newer artwork in physical coordinates')
    parser.add_argument('--margin-mm',type=float,default=.5)
    parser.add_argument('--region-gap-mm',type=float,default=.35,help='Grouping radius; does not change the subtraction masks')
    parser.add_argument('--crop-padding-mm',type=float,default=.35)
    parser.add_argument('--max-crops',type=int,default=12)
    parser.add_argument('--overview-columns',type=int,default=2)
    parser.add_argument('--preview-width',type=int,default=1100)
    parser.add_argument('--max-megapixels',type=float,default=60,help='Limit each raster canvas to this size; default 60 MP')
    parser.add_argument('--palette',help='JSON color palette; see examples/palette.json')
    parser.add_argument('--archive-tool',help='Path to 7-Zip or UnRAR for actual RAR input')
    args = parser.parse_args(argv)
    try:
        from .core import Options,compare,DEFAULT_PALETTE
        palette = json.loads(Path(args.palette).read_text(encoding='utf-8')) if args.palette else dict(DEFAULT_PALETTE)
        tolerance_mm = args.tolerance_mm if args.tolerance_mm is not None else .02
        if args.tolerance_pixels is not None:
            if args.dpmm <= 0: raise ValueError('Resolution must be positive.')
            tolerance_mm = args.tolerance_pixels/args.dpmm
        config = Options(dpmm=args.dpmm,tolerance_mm=tolerance_mm,threshold=args.threshold,
            scope=args.scope,missing=args.missing,margin_mm=args.margin_mm,region_gap_mm=args.region_gap_mm,
            crop_padding_mm=args.crop_padding_mm,max_crops=args.max_crops,overview_columns=args.overview_columns,
            preview_width=args.preview_width,max_megapixels=args.max_megapixels,new_offset_mm=tuple(args.new_offset_mm),
            palette=palette,layer_map=args.layer_map,archive_tool=args.archive_tool)
        compare(args.old,args.new,args.output,config,progress=lambda message:print(message,flush=True))
    except ImportError as error:
        print(f'Missing dependency: {error}. Run setup-windows.cmd or install requirements.txt.',file=sys.stderr)
        return 2
    except (ValueError,OSError,KeyError,TypeError) as error:
        print('Comparison failed: '+str(error),file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':
    sys.exit(main())

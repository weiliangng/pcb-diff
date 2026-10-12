import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcb_diff import __version__
parser=argparse.ArgumentParser()
parser.add_argument('tag')
parser.add_argument('--check-git-tag',action='store_true')
args=parser.parse_args()
project=tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
if project['project']['version'] != __version__:
    raise SystemExit('Project and application versions must match.')
if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?',args.tag) or args.tag != 'v'+__version__:
    raise SystemExit(f'Release tag must match the application version: v{__version__}')
if args.check_git_tag:
    refs=subprocess.run(['git','ls-remote','--tags','origin','refs/tags/'+args.tag,'refs/tags/'+args.tag+'^{}'],text=True,capture_output=True,check=True).stdout.splitlines()
    by_ref={line.split()[1]:line.split()[0] for line in refs}
    tag_sha=by_ref.get('refs/tags/'+args.tag+'^{}',by_ref.get('refs/tags/'+args.tag))
    current=subprocess.run(['git','rev-parse','HEAD'],text=True,capture_output=True,check=True).stdout.strip()
    if tag_sha is not None and tag_sha != current:
        raise SystemExit('Existing tag points to another commit; publish from that tag or choose a new version.')
if 'GITHUB_OUTPUT' in os.environ:
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as file:
        file.write(f'tag={args.tag}\nversion={__version__}\nprerelease={str("-" in args.tag).lower()}\n')
print('Validated release '+args.tag)

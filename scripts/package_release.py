"""Create a portable Windows ZIP and checksums for all release deliverables."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pcb_diff import __version__

root=Path(__file__).resolve().parents[1]
out=root/'release-assets'
out.mkdir(exist_ok=True)
license_text=[]
for dist in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
    name=dist.metadata['Name']
    if name.lower() in ('pip','setuptools','build','pyproject-hooks','packaging','pyinstaller-hooks-contrib'):
        continue
    license_text.append(f'\n{"="*72}\n{name} {dist.version}\nLicense expression: {dist.metadata.get("License-Expression",dist.metadata.get("License","See upstream distribution"))}\n')
    found=False
    for file in dist.files or []:
        if Path(str(file)).name.lower().startswith(('license','copying','notice')):
            path=dist.locate_file(file)
            if path.is_file():
                text=path.read_text(encoding='utf-8',errors='replace')
                license_text.append('\n'+str(file)+'\n'+text+'\n')
                found=True
    if not found:
        license_text.append(str(dist.metadata.get('License','License terms available from the upstream source listed in package metadata.'))+'\n')
        for key,value in dist.metadata.items():
            if key=='Project-URL':license_text.append(value+'\n')
third_party=''.join(license_text)
portable=out/f'pcb-diff-{__version__}-windows-x64.zip'
with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in ['PCB-Diff.exe','pcb-diff-cli.exe']:
        source=root/'dist'/name
        if not source.is_file():raise SystemExit('Missing executable: '+name)
        archive.write(source,name)
        shutil.copyfile(source,out/name)
    for name in ['README.md','VALIDATION.md']:
        archive.write(root/name,name)
    for path in sorted((root/'examples').glob('*.json')):
        archive.write(path,'examples/'+path.name)
    for path in sorted((root/'docs').rglob('*')):
        if path.is_file():
            archive.write(path,path.relative_to(root).as_posix())
    archive.writestr('THIRD-PARTY-LICENSES.txt',third_party)
(out/'THIRD-PARTY-LICENSES.txt').write_text(third_party,encoding='utf-8')
for pattern in ['*.whl','*.tar.gz']:
    for path in (root/'dist').glob(pattern):shutil.copyfile(path,out/path.name)
versions={d.metadata['Name']:d.version for d in metadata.distributions()}
(out/'build-dependencies.json').write_text(json.dumps(dict(sorted(versions.items())),indent=2),encoding='utf-8')
lines=[]
for path in sorted(out.iterdir()):
    if path.is_file() and path.name!='SHA256SUMS.txt':
        with path.open('rb') as file:
            lines.append(hashlib.file_digest(file,'sha256').hexdigest()+'  '+path.name)
(out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
print('Packaged release '+__version__)

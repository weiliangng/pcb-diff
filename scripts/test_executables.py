"""Run real comparisons through both frozen entry points before release."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--dist',default='dist')
args=parser.parse_args()
directory=Path(args.dist).resolve()
kwargs={}
if os.name=='nt':
    info=subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow=0
    kwargs['startupinfo']=info
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    code='%FSLAX45Y45*%\n%MOMM*%\n%ADD10C,1*%\nD10*\nX200000Y300000D03*\n'
    old,new=root/'old.gbr',root/'new.gbr'
    old.write_text(code+'M02*')
    new.write_text(code+'X500000Y600000D03*\nM02*')
    subprocess.run([str(directory/'pcb-diff-cli.exe'),'--version'],check=True,timeout=120,**kwargs)
    subprocess.run([str(directory/'pcb-diff-cli.exe'),str(old),str(new),'-o',str(root/'cli')],check=True,timeout=180,**kwargs)
    result=json.loads((root/'cli'/'results.json').read_text())
    assert result['layers'][0]['exact_added_mm2'] > 0
    assert result['layers'][0]['exact_removed_mm2'] == 0
    assert (root/'cli'/'overview-exact.png').is_file()
    assert (root/'cli'/'report.html').is_file()
    subprocess.run([str(directory/'PCB-Diff.exe'),'--self-test',str(root/'gui')],check=True,timeout=180,**kwargs)
    result=json.loads((root/'gui'/'gui-self-test.json').read_text())
    assert result['passed'],result
    assert result['report_enabled']
    assert (root/'gui'/'comparison'/'overview-exact.png').is_file()
print('Both packaged executables completed their comparisons successfully.')

import subprocess
import sys
if sys.platform!='win32':raise SystemExit('Build the Windows executables on Windows.')
for command in [
    [sys.executable,'-m','unittest','discover','-s','tests','-v'],
    [sys.executable,'-m','PyInstaller','--noconfirm','--clean','pcb-diff.spec'],
    [sys.executable,'scripts/test_executables.py'],
    [sys.executable,'-m','build'],
    [sys.executable,'scripts/package_release.py'],
]:subprocess.run(command,check=True)

# Two self-contained Windows executables: GUI and command line.
from pathlib import Path
root = Path(SPECPATH)
common = dict(
    pathex=[str(root)], binaries=[], datas=[], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['matplotlib', 'pytest', 'IPython', 'notebook', 'quart', 'hypercorn'],
    noarchive=False,
)
gui = Analysis([str(root / 'pcb_diff_gui.py')], **common)
gui_pyz = PYZ(gui.pure)
EXE(gui_pyz, gui.scripts, gui.binaries, gui.datas, [], name='PCB-Diff',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
cli = Analysis([str(root / 'pcb_diff.py')], **common)
cli_pyz = PYZ(cli.pure)
EXE(cli_pyz, cli.scripts, cli.binaries, cli.datas, [], name='pcb-diff-cli',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False)

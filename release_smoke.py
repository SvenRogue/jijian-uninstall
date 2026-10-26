"""Non-destructive release smoke test and artifact assembly."""
import ast
import hashlib
import marshal
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

root = Path(__file__).resolve().parent
exe = root/'dist'/'极简卸载'/'极简卸载.exe'
archive = CArchiveReader(str(exe))
with tempfile.TemporaryDirectory() as td:
    pyz = Path(td)/'check.pyz'
    pyz.write_bytes(archive.extract('PYZ.pyz'))
    reader = ZlibArchiveReader(str(pyz))
    engine = reader.extract('app.engine')
    functions = {c.co_name:c for c in engine.co_consts if hasattr(c, 'co_name')}
    assert 'Uninstaller' in functions
    assert '_system_task_wrapper' not in functions
    assert '_system_sweep_script' not in functions
    print('Frozen engine: corrected build, no SYSTEM task scripts')

output = root/'release-smoke.log'
with output.open('wb') as out:
    result = subprocess.run([str(exe), '--scan-only'], stdout=out, stderr=subprocess.STDOUT, timeout=90)
text = output.read_text(encoding='utf-8',errors='replace')
assert result.returncode == 0, text[-1500:]
assert 'TOTAL ' in text, text[-1500:]
print('Frozen read-only scan:', next(x for x in text.splitlines() if x.startswith('TOTAL ')))

# GUI startup: retain until a real top-level window has been observed.
import ctypes
from ctypes import wintypes
p = subprocess.Popen([str(exe)])
try:
    import time
    title = ''
    u = ctypes.WinDLL('user32')
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    @callback_type
    def callback(hwnd, _):
        global title
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == p.pid and u.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd,text,256)
            if text.value == '极简卸载':
                title=text.value
        return True
    for _ in range(40):
        assert p.poll() is None, 'GUI exited before showing a window'
        u.EnumWindows(callback,0)
        if title:
            break
        time.sleep(.25)
    assert title, 'No visible application window'
    print('GUI startup:',title)
finally:
    p.terminate()
    p.wait(timeout=10)

assets=root/'release_assets'
assets.mkdir(exist_ok=True)
import shutil
setup=root/'installer'/'极简卸载-安装程序-1.0.1-preview.1.exe'
shutil.copyfile(setup,assets/'JiJian-Uninstall-1.0.1-preview.1-Setup.exe')
portable=assets/'JiJian-Uninstall-1.0.1-preview.1-Portable.zip'
with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(exe.parent.rglob('*')):
        if path.is_file():
            z.write(path,path.relative_to(exe.parent.parent))
    for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md'):
        z.write(root/name,Path('极简卸载')/name)
checks=[]
for path in sorted(assets.iterdir()):
    if path.suffix not in ('.exe','.zip'):
        continue
    checks.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
    print('Asset:',path.name,path.stat().st_size)
(assets/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='ascii')

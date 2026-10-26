"""Collect license texts from installed build dependencies without modifying them."""
from pathlib import Path
import importlib.metadata as meta
import shutil
import sys

out = Path(__file__).resolve().parent / 'third_party_licenses'
out.mkdir(exist_ok=True)
for project in ('PyQt5', 'PyQt5-Qt5', 'PyQt5-sip', 'Pillow', 'pywin32', 'pyinstaller'):
    dist = meta.distribution(project)
    for entry in dist.files or []:
        name = Path(str(entry)).name.lower()
        if any(word in name for word in ('license', 'licence', 'copying', 'copyright')):
            src = Path(dist.locate_file(entry))
            if src.is_file():
                destination = out / project / Path(str(entry)).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, destination)
# Python's license covers the interpreter and bundled C libraries.
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file():
    shutil.copyfile(python_license, out/'Python-LICENSE.txt')
print('Collected', sum(p.is_file() for p in out.rglob('*')), 'license texts')

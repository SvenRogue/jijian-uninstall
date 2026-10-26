# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 极简卸载 (JiJian Uninstall)."""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

datas = [
    ("app/assets/jijian.ico", "assets"),
    ("app/assets/jijian_128.png", "assets"),
    ("app/assets/jijian_512.png", "assets"),
    ("LICENSE", "."),
    ("THIRD_PARTY_NOTICES.md", "."),
    ("third_party_licenses", "third_party_licenses"),
]

hiddenimports = collect_submodules("app") + [
    "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
    "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter",
    "win32com", "win32com.shell", "pythoncom",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngine",
        "PyQt5.QtQuick", "PyQt5.QtQml", "PyQt5.QtMultimedia", "PyQt5.QtMultimediaWidgets",
        "PyQt5.QtBluetooth", "PyQt5.QtDesigner", "PyQt5.QtNetworkAuth",
        "PyQt5.QtPositioning", "PyQt5.QtSerialPort", "PyQt5.QtSql", "PyQt5.QtTest",
        "PyQt5.QtOpenGL", "PyQt5.QtPrintSupport", "PyQt5.QtSvg",
        "tkinter", "matplotlib", "numpy", "scipy", "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="极简卸载",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="app/assets/jijian.ico",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="极简卸载",
)

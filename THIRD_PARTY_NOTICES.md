# Third-party notices

JiJian Uninstall source and original icon artwork: Copyright (C) 2026 SvenRogue.
Project license: GPL-3.0 (see LICENSE).

Dependencies distributed with the Windows builds:

| Component | License / upstream |
| --- | --- |
| PyQt5 / PyQt5-sip | GPL v3 (the GPL distribution is used; no commercial PyQt license is claimed). https://www.riverbankcomputing.com/software/pyqt/ |
| Qt 5 | LGPL v3 / GPL v3, depending on component. Only Qt Core, GUI and Widgets are used. https://www.qt.io/licensing/ |
| Python 3.12 | PSF License. https://docs.python.org/3/license.html |
| Pillow | MIT-CMU / HPND and bundled third-party notices. https://github.com/python-pillow/Pillow |
| pywin32 | Python Software Foundation License. https://github.com/mhammond/pywin32 |
| PyInstaller bootloader | GPL v2 with an exception allowing redistribution of bundled applications. https://pyinstaller.org/en/stable/license.html |
| Microsoft Visual C++ runtime | Microsoft redistributable runtime terms, supplied with Python / Qt binaries. |
| Inno Setup | Inno Setup license. https://jrsoftware.org/files/is/license.txt |

The program calls Windows PowerShell and optionally winget already installed on the user's system. These tools and vendor uninstallers are not part of this source repository.

The `third_party_licenses` directory in binary distributions contains the available dependency license texts collected from the build environment. Corresponding application source is included with the GitHub release tag; upstream component source is available through the links above. Qt DLLs remain separate in `_internal`, so they can be replaced with compatible builds.

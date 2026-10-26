"""Entry point for 极简卸载 (JiJian Uninstall)."""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

# make `python main.py` work from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _resource_base() -> Path:
    """Project root when run from source, PyInstaller _MEIPASS when frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from app import theme
from app.ui import MainWindow


def main() -> int:
    # a frozen windowed build has no console: sys.stdout may be None, and any
    # print/stderr write from a worker thread would kill the process.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            setattr(sys, stream_name, open(os.devnull, "w", encoding="utf-8"))
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # diagnostics / automation entry point: `--scan-only` prints the scan result
    if "--scan-only" in sys.argv:
        from app import scanner
        scanner._diag("--- scan-only start ---")
        apps = scanner.scan_all(progress=lambda m: print(m, flush=True))
        for a in apps:
            print(f"{a.score:3d}  {a.uninstall_type:8s}  {a.name}", flush=True)
        print(f"TOTAL {len(apps)}", flush=True)
        return 0

    if "--trace" in sys.argv:
        import traceback
        log = os.path.join(os.environ.get("TEMP", "."), "jijian_trace.txt")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(f"frozen={getattr(sys, 'frozen', False)}\n")
            fh.write(f"argv={sys.argv!r}\n")
            fh.write(f"LOCALAPPDATA={os.environ.get('LOCALAPPDATA')!r}\n")
            try:
                from app import scanner
                fh.write(f"scanner={getattr(scanner, '__file__', '?')}\n")
                fh.write(f"has _diag={hasattr(scanner, '_diag')}\n")
                fh.write("arp=" + str(len(scanner.scan_arp())) + "\n")
                fh.write("store=" + str(len(scanner.scan_store())) + "\n")
                fh.write("winget=" + str(len(scanner.scan_winget())) + "\n")
            except Exception:
                fh.write("FAILED\n" + traceback.format_exc())
        return 0

    if sys.platform == "win32":
        # per-monitor DPI awareness so the glass UI stays crisp on scaled displays
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        # own taskbar identity so the window icon is ours, not python's
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "SvenRogue.JiJianUninstall.1")
        except Exception:
            pass

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("极简卸载")
    app.setApplicationDisplayName("极简卸载")
    app.setOrganizationName("SvenRogue")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.app_qss())

    icon_path = _resource_base() / "app" / "assets" / "jijian.ico"
    if not icon_path.exists():
        icon_path = _resource_base() / "assets" / "jijian.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    w = MainWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())

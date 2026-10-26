"""AppDelegate 用的图标解析器（与界面分离，便于单测）。"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtCore import QFileInfo, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication, QFileIconProvider

from .scanner import AppEntry

_provider: QFileIconProvider | None = None
_cache: dict[str, QIcon] = {}


def _get_provider() -> QFileIconProvider:
    global _provider
    if _provider is None:
        _provider = QFileIconProvider()
    return _provider


def icon_candidates(entry: AppEntry) -> list[str]:
    out: list[str] = []
    di = (entry.display_icon or "").strip().strip('"')
    if di:
        out.append(di.split(",")[0].strip().strip('"'))
    loc = (entry.install_location or "").strip().strip('"')
    if not loc:
        from .scanner import _derive_install_location
        loc = _derive_install_location(entry) or ""
    if loc and os.path.isdir(loc):
        try:
            base = (entry.name or "").lower().replace(" ", "")
            exes = sorted(
                (f for f in os.listdir(loc) if f.lower().endswith(".exe")),
                key=lambda f: (0 if base and base[:5] in f.lower() else 1, len(f)),
            )
            out += [os.path.join(loc, e) for e in exes[:3]]
        except OSError:
            pass
    fam = getattr(entry, "_pkg_family", "")
    if fam:
        pkg = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / fam
        if pkg.is_dir():
            out.append(str(pkg))
    return out


def app_icon(entry: AppEntry) -> QIcon:
    if entry.uid in _cache:
        return _cache[entry.uid]
    icon = QIcon()
    for cand in icon_candidates(entry):
        try:
            if cand and os.path.exists(cand):
                cand_icon = _get_provider().icon(QFileInfo(cand))
                if not cand_icon.isNull() and not cand_icon.pixmap(32, 32).isNull():
                    icon = cand_icon
                    break
        except Exception:
            continue
    if icon.isNull():
        style = QApplication.style()
        icon = style.standardIcon(style.SP_FileIcon)
    _cache[entry.uid] = icon
    return icon


def rounded_pixmap(icon: QIcon, size: int, radius: int = 9) -> QPixmap:
    scale = 2
    src = icon.pixmap(QSize(size * scale, size * scale))
    if src.isNull():
        src = QPixmap(size * scale, size * scale)
        src.fill(Qt.transparent)
    src = src.scaled(size * scale, size * scale, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(size * scale, size * scale)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size * scale, size * scale, radius * scale, radius * scale)
    p.setClipPath(path)
    p.drawPixmap(0, 0, src)
    p.end()
    out.setDevicePixelRatio(scale)
    return out


def app_pixmap(entry: AppEntry, size: int) -> QPixmap:
    return rounded_pixmap(app_icon(entry), size)

"""Resolve real app icons without accepting directory icons as application icons."""
from __future__ import annotations
import ctypes
import ntpath
import os
import re
import sys
from pathlib import Path
from PyQt5.QtCore import QFileInfo, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication, QFileIconProvider
from .scanner import AppEntry
from .drive_label import _expand

_provider = None
_cache = {}


def _get_provider():
    global _provider
    if _provider is None:
        _provider = QFileIconProvider()
    return _provider


def parse_display_icon(value):
    """Parse a quoted or unquoted icon path and its trailing resource index."""
    raw = _expand((value or '').strip())
    match = re.match(r'^\s*"([^"]+)"\s*(?:,\s*(-?\d+)\s*)?$', raw)
    if match:
        return match.group(1), int(match.group(2) or 0)
    match = re.match(r'^(.*?)(?:,\s*(-?\d+))?\s*$', raw)
    if not match or '"' in raw:
        return '', 0
    return match.group(1).strip(), int(match.group(2) or 0)


def icon_candidates(entry):
    out = []
    icon, index = parse_display_icon(entry.display_icon)
    if icon and os.path.isfile(icon):
        out.append((icon, index))
    logo = getattr(entry, '_logo_path', '')
    if logo and os.path.isfile(logo):
        out.append((logo, 0))
    loc = _expand((entry.install_location or '').strip().strip('"'))
    if loc and os.path.isdir(loc):
        try:
            files = [f for f in os.listdir(loc) if f.lower().endswith('.exe')]
            # Never pick an uninstaller/update/helper as the product icon.
            files = [f for f in files if not re.search(r'unins|uninstall|setup|update|repair|helper|crash|service',f,re.I)]
            product = re.sub(r'[^a-z0-9]', '', entry.name.lower())
            def rank(filename):
                stem = re.sub(r'[^a-z0-9]', '', Path(filename).stem.lower())
                return (0 if product and (stem == product or stem in product or product in stem) else 1, len(filename), filename.lower())
            for f in sorted(files,key=rank)[:8]:
                out.append((os.path.join(loc,f),0))
        except OSError:
            pass
    return out


def _resource_icon(path, index):
    if sys.platform != 'win32' or ntpath.splitext(path)[1].lower() not in ('.exe','.dll','.icl'):
        return QIcon()
    try:
        import win32gui
        from PyQt5.QtWinExtras import QtWin
        large, small = win32gui.ExtractIconEx(path, index, 1)
        handles = large + small
        if not handles:
            return QIcon()
        try:
            pixmap = QtWin.fromHICON(handles[0])
            return QIcon(pixmap) if not pixmap.isNull() else QIcon()
        finally:
            for h in handles:
                win32gui.DestroyIcon(h)
    except Exception:
        return QIcon()


def app_icon(entry):
    candidates = icon_candidates(entry)
    key = (entry.uid, entry.version, tuple(candidates))
    if key in _cache:
        return _cache[key]
    for path, index in candidates:
        try:
            ext = ntpath.splitext(path)[1].lower()
            icon = _resource_icon(path, index) if ext in ('.exe','.dll','.icl') else QIcon(path)
            if icon.isNull() and index == 0 and ext == '.exe':
                icon = _get_provider().icon(QFileInfo(path))
            if not icon.isNull() and not icon.pixmap(32,32).isNull():
                _cache[key] = icon
                return icon
        except Exception:
            continue
    # A neutral file glyph is more honest than a folder or another application's icon.
    style = QApplication.style()
    return style.standardIcon(style.SP_FileIcon)


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

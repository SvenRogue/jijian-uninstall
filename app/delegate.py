"""ChatGPT-desktop-style list row for the application rail.

Plain rows (not cards): icon, title, secondary line and a right-aligned size,
with a rounded hover/selection fill. Selected rows invert to the accent colour
like ChatGPT's conversation list.
"""
from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from . import theme
from .icons import app_pixmap
from .scanner import AppEntry, human_size

ROW_H = 50
ICON = 30


class AppDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        entry = index.data(Qt.UserRole)
        if entry is None:
            super().paint(painter, option, index)
            return
        c = theme.palette()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = QRectF(option.rect).adjusted(6, 1, -6, -1)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        if selected or hovered:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            painter.fillPath(path, QColor(c["row_hover"]))

        ix = r.left() + 8
        iy = r.top() + (r.height() - ICON) / 2
        painter.drawPixmap(int(ix), int(iy), ICON, ICON, app_pixmap(entry, ICON))

        tx = ix + ICON + 10
        avail = max(60, int(r.right() - 8 - tx))

        name_font = QFont(painter.font())
        name_font.setPointSizeF(9.6)
        name_font.setWeight(QFont.Medium)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        name = fm.elidedText(entry.name or "未知应用", Qt.ElideRight, avail)
        painter.setPen(QColor(c["text"]))
        painter.drawText(QRectF(tx, r.top() + 7, avail, 17),
                         int(Qt.AlignLeft | Qt.AlignVCenter), name)

        sub_font = QFont(painter.font())
        sub_font.setPointSizeF(8.2)
        sub_font.setWeight(QFont.Normal)
        painter.setFont(sub_font)
        fm2 = QFontMetrics(sub_font)
        bits = []
        if entry.version:
            bits.append("v" + entry.version)
        if entry.publisher:
            bits.append(entry.publisher)
        if not bits:
            bits.append(_engine_label(entry))
        tag = _badge_text(entry)
        if tag:
            bits.append(tag)
        sub = fm2.elidedText(" · ".join(bits), Qt.ElideRight, avail)
        painter.setPen(QColor(c["text3"]))
        painter.drawText(QRectF(tx, r.top() + 25, avail, 15),
                         int(Qt.AlignLeft | Qt.AlignVCenter), sub)

        # hairline between rows, inset past the icon (ChatGPT's rail rhythm)
        if not selected and not hovered:
            painter.setPen(QPen(QColor(c["sep"]), 1))
            y = r.bottom() + 1
            painter.drawLine(int(tx), int(y), int(r.right() - 6), int(y))
        painter.restore()


def _engine_label(entry: AppEntry) -> str:
    return {"nsis": "静默卸载", "inno": "静默卸载", "msiexec": "MSI",
            "appx": "商店应用", "winget": "winget",
            "custom": "交互卸载"}.get(entry.uninstall_type, "应用")


def _badge_text(entry: AppEntry) -> str:
    total = entry.total_leftover
    if total > 0:
        return human_size(total)
    if entry.size > 0:
        return human_size(entry.size * 1024)
    return ""

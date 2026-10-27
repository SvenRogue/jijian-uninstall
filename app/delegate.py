"""Apple-style list row for the application sidebar.

Rows are plain list rows (not cards): icon, name, secondary line and a right
aligned size, with a rounded selection fill and a hairline separator, matching
macOS System Settings / App Store list rhythm.
"""
from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                         QPen)
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from . import theme
from .icons import app_pixmap
from .scanner import AppEntry, human_size

ROW_H = 52
ICON = 34


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
        r = QRectF(option.rect).adjusted(2, 1, -2, -1)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        if selected:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 1, -2, -1), 7, 7)
            painter.fillPath(path, QColor(c["accent"]))
        elif hovered:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 1, -2, -1), 7, 7)
            painter.fillPath(path, QColor(c["row_hover"]))

        ix = r.left() + 10
        iy = r.top() + (r.height() - ICON) / 2
        pm = app_pixmap(entry, ICON)
        painter.drawPixmap(int(ix), int(iy), ICON, ICON, pm)

        tx = ix + ICON + 11
        right_reserved = 82
        avail = max(60, int(r.right() - right_reserved - tx))

        name_font = QFont(painter.font())
        name_font.setPointSizeF(9.9)
        name_font.setWeight(QFont.DemiBold)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        name = fm.elidedText(entry.name or "未知应用", Qt.ElideRight, avail)
        painter.setPen(QColor(c["on_accent"] if selected else c["text"]))
        painter.drawText(QRectF(tx, r.top() + 8, avail, 18),
                         int(Qt.AlignLeft | Qt.AlignVCenter), name)

        sub_font = QFont(painter.font())
        sub_font.setPointSizeF(8.3)
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
        sub = fm2.elidedText(" · ".join(bits), Qt.ElideRight, avail)
        painter.setPen(QColor(255, 255, 255, 200) if selected else QColor(c["text2"]))
        painter.drawText(QRectF(tx, r.top() + 27, avail, 15),
                         int(Qt.AlignLeft | Qt.AlignVCenter), sub)

        tag = _badge_text(entry)
        if tag:
            little = QFont(painter.font())
            little.setPointSizeF(8.2)
            painter.setFont(little)
            fml = QFontMetrics(little)
            w = fml.horizontalAdvance(tag)
            painter.setPen(QColor(255, 255, 255, 220) if selected else QColor(c["text3"]))
            painter.drawText(QRectF(r.right() - 12 - w, r.top() + 17, w, 16),
                             int(Qt.AlignRight | Qt.AlignVCenter), tag)

        # hairline separator, inset past the icon like macOS lists
        if not selected:
            painter.setPen(QPen(QColor(c["sep"]), 1))
            y = r.bottom()
            painter.drawLine(int(tx), int(y), int(r.right() - 10), int(y))
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

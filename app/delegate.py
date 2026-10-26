"""应用列表卡片绘制。"""
from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                         QPainterPath, QPen)
from PyQt5.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .icons import app_pixmap
from .scanner import AppEntry, human_size

CARD_H = 64
ICON = 38


class AppDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), CARD_H + 8)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        entry = index.data(Qt.UserRole)
        if entry is None:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = option.rect.adjusted(2, 4, -2, -4)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 12, 12)
        if selected:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor(108, 140, 255, 62))
            g.setColorAt(1, QColor(108, 140, 255, 20))
            painter.fillPath(path, g)
            painter.setPen(QPen(QColor(108, 140, 255, 170), 1))
            painter.drawPath(path)
        elif hovered:
            painter.fillPath(path, QColor(255, 255, 255, 22))
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1))
            painter.drawPath(path)
        else:
            painter.fillPath(path, QColor(255, 255, 255, 12))

        ix = r.left() + 13
        iy = r.top() + (r.height() - ICON) // 2
        pm = app_pixmap(entry, ICON)
        painter.drawPixmap(ix, iy, int(pm.width() / max(1, pm.devicePixelRatio())),
                           int(pm.height() / max(1, pm.devicePixelRatio())), pm)

        tx = ix + ICON + 13
        right_reserved = 122
        avail = max(70, r.right() - right_reserved - tx)

        name_font = QFont(painter.font())
        name_font.setPointSizeF(10.2)
        name_font.setWeight(QFont.DemiBold)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        name = fm.elidedText(entry.name or "未知应用", Qt.ElideRight, avail)
        painter.setPen(QColor("#EDF0F7"))
        painter.drawText(QRectF(tx, r.top() + 10, avail, 20),
                         int(Qt.AlignLeft | Qt.AlignVCenter), name)

        sub_font = QFont(painter.font())
        sub_font.setPointSizeF(8.6)
        sub_font.setWeight(QFont.Normal)
        painter.setFont(sub_font)
        fm2 = QFontMetrics(sub_font)
        bits = []
        if entry.version:
            bits.append("v" + entry.version)
        if entry.publisher:
            bits.append(entry.publisher)
        sub = " · ".join(bits) if bits else "未知发布者"
        sub = fm2.elidedText(sub, Qt.ElideRight, avail)
        painter.setPen(QColor("#8A93A8"))
        painter.drawText(QRectF(tx, r.top() + 31, avail, 17),
                         int(Qt.AlignLeft | Qt.AlignVCenter), sub)

        # right column: size badge on top, engine label below
        bx_right = r.right() - 13
        tag = _badge_text(entry)
        if tag:
            bw = 14 + fm2.horizontalAdvance(tag)
            badge = QRectF(bx_right - bw, r.top() + 10, bw, 18)
            bpath = QPainterPath()
            bpath.addRoundedRect(badge, 9, 9)
            painter.fillPath(bpath, QColor(108, 140, 255, 38))
            painter.setPen(QColor("#9DB0FF"))
            painter.drawText(badge, int(Qt.AlignCenter), tag)

        engine = {"nsis": "静默卸载", "inno": "静默卸载", "msiexec": "MSI",
                  "appx": "商店应用", "winget": "winget",
                  "custom": "交互卸载"}.get(entry.uninstall_type, "")
        if engine:
            little = QFont(painter.font())
            little.setPointSizeF(8.0)
            painter.setFont(little)
            fml = QFontMetrics(little)
            w = fml.horizontalAdvance(engine)
            painter.setPen(QColor("#5E6577"))
            painter.drawText(QRectF(bx_right - w, r.top() + 32, w, 16),
                             int(Qt.AlignRight | Qt.AlignVCenter), engine)

        painter.restore()


def _badge_text(entry: AppEntry) -> str:
    total = entry.total_leftover
    if total > 0:
        return human_size(total)
    if entry.size > 0:
        return human_size(entry.size * 1024)
    return ""

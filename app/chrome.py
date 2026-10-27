"""ChatGPT-desktop-style sidebar widgets.

The window chrome is Windows-native (real title bar, system min/max/close), so
this module only provides the in-canvas building blocks: section labels, a
search field with a leading glyph, an exclusive segmented control, cards and a
small activity ring.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PyQt5.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import theme


class LogoWidget(QWidget):
    """App icon, resolved for both source runs and a frozen build."""

    def __init__(self, size=22, parent=None):
        super().__init__(parent)
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        pix = QPixmap()
        for cand in (base / "app" / "assets" / "jijian_128.png",
                     base / "assets" / "jijian_128.png",
                     Path(__file__).resolve().parent / "assets" / "jijian_128.png"):
            if cand.exists():
                pix = QPixmap(str(cand))
                break
        self._pix = pix
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        if self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, self.width(), self.height(), self._pix)
        p.end()


class Spinner(QWidget):
    """Thin activity ring shown next to the status text while working."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(13, 13)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 24) % 360
        self.update()

    def start(self):
        self.show()
        self._timer.start(28)

    def stop(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, event):
        c = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        p.setPen(QPen(QColor(c["track"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
        p.setPen(QPen(QColor(c["text2"]), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, int(-self._angle * 16), int(110 * 16))
        p.end()


class SegmentedControl(QWidget):
    """Exclusive segmented control (macOS/ChatGPT style), emits the new key."""

    changed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("Segment")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(1)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            b = QPushButton(label)
            b.setObjectName("SegmentItem")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_value(k, emit=True))
            lay.addWidget(b)
            self._buttons[key] = b
        self._value = options[0][0] if options else ""
        if self._buttons:
            self._buttons[self._value].setChecked(True)

    def value(self) -> str:
        return self._value

    def set_value(self, key: str, emit: bool = False):
        if key not in self._buttons:
            return
        self._value = key
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        if emit:
            self.changed.emit(key)

    def set_options_enabled(self, enabled: bool):
        for b in self._buttons.values():
            b.setEnabled(enabled)


class SearchField(QWidget):
    """QLineEdit with a leading magnifier drawn inside the field."""

    textChanged = pyqtSignal(str)

    def __init__(self, placeholder="搜索", parent=None):
        super().__init__(parent)
        self.edit = QLineEdit()
        self.edit.setObjectName("Search")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(self.textChanged.emit)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit)

    def text(self) -> str:
        return self.edit.text()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.edit.setEnabled(enabled)

    def paintEvent(self, event):
        super().paintEvent(event)
        c = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = p.pen()
        pen.setColor(QColor(c["text3"]))
        pen.setWidthF(1.4)
        p.setPen(pen)
        x, y = 11.0, 12.5
        p.drawEllipse(QRectF(x, y - 4.0, 7.2, 7.2))
        p.drawLine(int(x + 6.4), int(y + 2.6), int(x + 9.4), int(y + 5.6))
        p.end()


class Card(QWidget):
    """Grouped card: optional section label above a rounded container."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        if title:
            lab = QLabel(title)
            lab.setProperty("role", "section")
            outer.addWidget(lab)
        self.frame = QFrame()
        self.frame.setObjectName("Card")
        self.body = QVBoxLayout(self.frame)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        outer.addWidget(self.frame)

    def add(self, widget: QWidget, last: bool = False):
        row = QFrame()
        row.setObjectName("CardRow")
        row.setProperty("last", "true" if last else "false")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)
        lay.addWidget(widget)
        self.body.addWidget(row)
        return row

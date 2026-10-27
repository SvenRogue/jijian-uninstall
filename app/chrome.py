"""Apple-style sidebar and window chrome widgets."""
from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

from . import theme


class TrafficLights(QWidget):
    """Three macOS-style window buttons. Emits actions instead of drawing menus."""

    close_clicked = pyqtSignal()
    min_clicked = pyqtSignal()
    max_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for key, glyph, signal in (("close", "✕", self.close_clicked),
                                   ("min", "—", self.min_clicked),
                                   ("max", "＋", self.max_clicked)):
            b = QPushButton(glyph)
            b.setObjectName("Traffic")
            b.setProperty("light", key)
            b.setCursor(Qt.ArrowCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip({"close": "关闭", "min": "最小化", "max": "缩放"}[key])
            b.clicked.connect(signal.emit)
            lay.addWidget(b)
        lay.addStretch(1)


class LogoWidget(QWidget):
    def __init__(self, size=22, parent=None):
        super().__init__(parent)
        from pathlib import Path
        import sys
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        pix = None
        for cand in (base / "app" / "assets" / "jijian_128.png", base / "assets" / "jijian_128.png",
                     Path(__file__).resolve().parent / "assets" / "jijian_128.png"):
            if cand.exists():
                pix = QPixmap(str(cand))
                break
        self._pix = pix if pix is not None else QPixmap()
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        if self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, self.width(), self.height(), self._pix)
        p.end()


class Spinner(QWidget):
    """Thin macOS-style activity ring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(14, 14)
        from PyQt5.QtCore import QTimer
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

    def paintEvent(self, e):
        from PyQt5.QtGui import QPen
        c = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        p.setPen(QPen(QColor(c["track"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
        p.setPen(QPen(QColor(c["accent"]), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, int(-self._angle * 16), int(110 * 16))
        p.end()


class SegmentedControl(QWidget):
    """macOS segmented control: one selected segment, exclusive."""

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


class SidebarSection(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "section")


class SearchField(QWidget):
    """QLineEdit with a leading magnifier drawn inside the field."""

    textChanged = pyqtSignal(str)

    def __init__(self, placeholder="搜索", parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QLineEdit
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
        x, y = 11.0, 12.0
        p.drawEllipse(QRectF(x, y - 4.2, 7.4, 7.4))
        p.drawLine(int(x + 6.6), int(y + 2.4), int(x + 9.6), int(y + 5.6))
        p.end()


class Card(QWidget):
    """Grouped card container: optional title, rows added by the caller."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QFrame
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)
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
        from PyQt5.QtWidgets import QFrame
        row = QFrame()
        row.setObjectName("CardRow")
        row.setProperty("last", "true" if last else "false")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(13, 10, 13, 10)
        lay.setSpacing(11)
        lay.addWidget(widget)
        self.body.addWidget(row)
        return row

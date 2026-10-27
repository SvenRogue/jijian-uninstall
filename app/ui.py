"""主窗口：无边框暗色玻璃风格，三段式 —— 应用列表 / 残留详情 / 执行日志。"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize,
                          Qt, QThread, QTimer, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPixmap)
from PyQt5.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QGraphicsDropShadowEffect,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSizeGrip, QStackedWidget, QVBoxLayout, QWidget)

from . import engine as eng
from . import scanner, theme
from .delegate import AppDelegate
from .icons import app_pixmap
from .scanner import AppEntry, human_size


# ------------------------------------------------------------------ helpers
def asset(name: str) -> str:
    """Resolve a bundled asset for both source runs and a frozen build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for cand in (base / "app" / "assets" / name, base / "assets" / name,
                 Path(__file__).resolve().parent / "assets" / name):
        if cand.exists():
            return str(cand)
    return str(base / "app" / "assets" / name)


def _shadow(w, blur=34, dy=8, alpha=120):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(eff)
    return eff


class LogoWidget(QWidget):
    def __init__(self, size=26, parent=None):
        super().__init__(parent)
        self._pix = QPixmap(asset("jijian_128.png"))
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, self._pix.scaled(self._size, self._size, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))
        p.end()


class Spinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(22, 22)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def start(self):
        self.show()
        self._timer.start(16)

    def stop(self):
        self._timer.stop()
        self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2, 2, self.width() - 4, self.height() - 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawEllipse(r)
        pen_pen = p
        from PyQt5.QtGui import QPen
        pen_pen.setPen(QPen(QColor(108, 140, 255), 2.6))
        p.setBrush(Qt.NoBrush)
        p.drawArc(r, int(-self._angle * 16), int(100 * 16))
        p.end()


# ------------------------------------------------------------------ workers
class ScanWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def run(self):
        try:
            apps = scanner.scan_all(progress=lambda m: self.progress.emit(m))
            self.done.emit(apps)
        except Exception as e:  # pragma: no cover
            self.failed.emit(f"{type(e).__name__}: {e}")


class InventoryWorker(QThread):
    done = pyqtSignal(object)

    def __init__(self, entry: AppEntry):
        super().__init__()
        self.entry = copy.deepcopy(entry)

    def run(self):
        try:
            self.done.emit(scanner.inventory(self.entry))
        except Exception:
            self.done.emit(self.entry)


class UninstallWorker(QThread):
    logline = pyqtSignal(str)
    pct = pyqtSignal(int)
    finished_report = pyqtSignal(object)

    def __init__(self, entry: AppEntry, opts: dict):
        super().__init__()
        self.entry = copy.deepcopy(entry)
        self.opts = opts

    def run(self):
        u = eng.Uninstaller(self.logline.emit, self.pct.emit)
        try:
            rep = u.run(self.entry, dry_run=self.opts.get("dry", False),
                        do_registry=self.opts.get("registry", True),
                        do_appdata=self.opts.get("appdata", True),
                        do_shortcuts=self.opts.get("shortcuts", True))
        except Exception as e:
            rep = eng.Report(app_name=self.entry.name)
            self.logline.emit(f"✗ 异常：{type(e).__name__}: {e}")
            rep.failed.append(("engine", str(e)))
        self.finished_report.emit(rep)


# ------------------------------------------------------------------ window
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("极简卸载")
        self.setWindowIcon(QIcon(asset("jijian.ico")))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(920, 600)
        self.resize(1040, 700)

        self._drag_pos: QPoint | None = None
        self.apps: list[AppEntry] = []
        self.current: AppEntry | None = None
        self._scan_worker = None
        self._inv_worker = None
        self._uninst_worker = None
        self._filter = "all"
        self._busy = False
        self._workers = set()
        self._closing = False
        self._inventory_ready = set()
        self._inventory_epoch = 0

        self._build_ui()
        QTimer.singleShot(180, self.start_scan)

    # ---------------------------------------------------------------- ui
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.shell = QWidget()
        self.shell.setObjectName("Shell")
        outer.addWidget(self.shell)
        root = QVBoxLayout(self.shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        _shadow(self.shell, blur=48, dy=10, alpha=150)

        root.addWidget(self._build_titlebar())
        root.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(22, 4, 22, 16)
        body.setSpacing(16)

        # left: list
        left = QVBoxLayout()
        left.setSpacing(8)
        hdr = QHBoxLayout()
        self.lbl_count = QLabel("正在扫描…")
        self.lbl_count.setProperty("role", "sub")
        hdr.addWidget(self.lbl_count)
        hdr.addStretch(1)
        left.addLayout(hdr)

        self.list = QListWidget()
        self.list.setObjectName("AppList")
        self.list.setItemDelegate(AppDelegate())
        self.list.setSpacing(0)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list, 1)

        self.empty_hint = QLabel("没有匹配的应用")
        self.empty_hint.setProperty("role", "faint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.hide()
        left.addWidget(self.empty_hint)

        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(470)
        body.addWidget(lw)

        # right: detail + log
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self._build_detail())
        right.addWidget(self._build_log(), 1)
        body.addLayout(right, 1)

        root.addLayout(body, 1)
        root.addWidget(self._build_statusbar())

    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.mousePressEvent = self._tb_press          # type: ignore[assignment]
        bar.mouseMoveEvent = self._tb_move            # type: ignore[assignment]
        bar.mouseReleaseEvent = self._tb_release      # type: ignore[assignment]
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 10, 0)
        lay.setSpacing(10)

        lay.addWidget(LogoWidget(24))
        t = QLabel("极简卸载")
        t.setProperty("role", "title")
        lay.addWidget(t)
        sub = QLabel("JiJian Uninstall")
        sub.setProperty("role", "faint")
        lay.addWidget(sub)
        lay.addStretch(1)

        self.btn_admin = QPushButton("非管理员")
        self.btn_admin.setObjectName("Pill")
        self.btn_admin.setToolTip("点击以管理员身份重新启动（清理受保护目录需要）")
        self.btn_admin.clicked.connect(self._on_admin_click)
        lay.addWidget(self.btn_admin)
        self._refresh_admin_badge()

        lay.addSpacing(6)
        for txt, name, cb in (("—", "Min", self.showMinimized),
                              ("□", "Max", self._toggle_max),
                              ("×", "Close", self.close)):
            b = QPushButton(txt)
            b.setObjectName("WinBtn")
            b.setProperty("class", name)
            b.clicked.connect(cb)
            lay.addWidget(b)
        return bar

    def _build_toolbar(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(22, 2, 22, 10)
        lay.setSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("搜索应用、发布者…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search, 1)

        self.pills: dict[str, QPushButton] = {}
        for key, label in (("all", "全部"), ("big", "大体积"), ("residue", "有残留风险"),
                           ("store", "商店应用")):
            b = QPushButton(label)
            b.setObjectName("Pill")
            b.setCheckable(True)
            b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self.pills[key] = b
            lay.addWidget(b)

        self.btn_rescan = QPushButton("重新扫描")
        self.btn_rescan.setObjectName("Pill")
        self.btn_rescan.clicked.connect(self.start_scan)
        lay.addWidget(self.btn_rescan)
        return w

    def _build_detail(self) -> QWidget:
        card = QFrame()
        card.setObjectName("DetailCard")
        card.setStyleSheet(
            "QFrame#DetailCard{background:rgba(255,255,255,0.035);border:1px solid "
            "rgba(255,255,255,0.075);border-radius:14px;}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.d_icon = QLabel()
        self.d_icon.setFixedSize(44, 44)
        top.addWidget(self.d_icon, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.d_name = QLabel("选择一个应用")
        self.d_name.setProperty("role", "h1")
        self.d_name.setWordWrap(False)
        col.addWidget(self.d_name)
        self.d_meta = QLabel("")
        self.d_meta.setProperty("role", "sub")
        col.addWidget(self.d_meta)
        top.addLayout(col, 1)
        lay.addLayout(top)

        # leftover summary row
        sumrow = QHBoxLayout()
        sumrow.setSpacing(8)
        self.d_sum = QLabel("")
        self.d_sum.setProperty("role", "sub")
        sumrow.addWidget(self.d_sum)
        sumrow.addStretch(1)
        lay.addLayout(sumrow)

        # leftover scroll list
        self.lo_area = QScrollArea()
        self.lo_area.setWidgetResizable(True)
        self.lo_area.setFrameShape(QFrame.NoFrame)
        self.lo_area.setStyleSheet("QScrollArea{background:transparent;}")
        self.lo_host = QWidget()
        self.lo_host.setStyleSheet("background:transparent;")
        self.lo_lay = QVBoxLayout(self.lo_host)
        self.lo_lay.setContentsMargins(0, 0, 0, 0)
        self.lo_lay.setSpacing(2)
        self.lo_lay.addStretch(1)
        self.lo_area.setWidget(self.lo_host)
        self.lo_area.setMinimumHeight(96)
        self.lo_area.setMaximumHeight(150)
        lay.addWidget(self.lo_area)

        # options + action
        opt = QHBoxLayout()
        opt.setSpacing(14)
        notice = QLabel('卸载后重新扫描并选择')
        notice.setToolTip('此处清点仅供参考；不会直接清理。')
        opt.addWidget(notice)
        self.cb_reg = QCheckBox("注册表")
        self.cb_data = QCheckBox("数据与缓存")
        self.cb_link = QCheckBox("快捷方式")
        for cb in (self.cb_reg, self.cb_data, self.cb_link):
            cb.setChecked(False)
            cb.hide()
        opt.addStretch(1)
        self.btn_dry = QPushButton("演练")
        self.btn_dry.setObjectName("Ghost")
        self.btn_dry.setToolTip("只显示将要做什么，不做任何修改")
        self.btn_dry.clicked.connect(lambda: self._start_uninstall(dry=True))
        opt.addWidget(self.btn_dry)
        self.btn_go = QPushButton("卸载向导")
        self.btn_go.setObjectName("Primary")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.clicked.connect(lambda: self._start_uninstall(dry=False))
        opt.addWidget(self.btn_go)
        lay.addLayout(opt)
        return card

    def _build_log(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame{background:transparent;border:none;}")
        wrap.setMinimumHeight(190)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        hdr = QHBoxLayout()
        hdr.setContentsMargins(2, 0, 2, 0)
        t = QLabel("执行日志")
        t.setProperty("role", "h2")
        hdr.addWidget(t)
        hdr.addStretch(1)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setProperty("role", "faint")
        hdr.addWidget(self.lbl_status)
        lay.addLayout(hdr)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        lay.addWidget(self.log, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)
        return wrap

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(46)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 0, 8, 0)
        lay.setSpacing(10)
        self.spinner = Spinner()
        self.spinner.hide()
        lay.addWidget(self.spinner)
        self.lbl_foot = QLabel("")
        self.lbl_foot.setProperty("role", "faint")
        lay.addWidget(self.lbl_foot)
        lay.addStretch(1)
        self.btn_recovery = QPushButton("恢复中心")
        self.btn_recovery.setObjectName("Pill")
        self.btn_recovery.clicked.connect(self._open_recovery)
        lay.addWidget(self.btn_recovery)
        self.btn_open_logs = QPushButton("日志目录")
        self.btn_open_logs.setObjectName("Pill")
        self.btn_open_logs.clicked.connect(self._open_logs)
        lay.addWidget(self.btn_open_logs)
        grip = QSizeGrip(bar)
        lay.addWidget(grip, 0, Qt.AlignBottom)
        return bar

    # ------------------------------------------------------- window drag
    def _tb_press(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            if self.isMaximized():
                self.showNormal()
                self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            self.move(e.globalPos() - self._drag_pos)

    def _tb_release(self, e):
        self._drag_pos = None

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ------------------------------------------------------------ admin
    def _refresh_admin_badge(self):
        if eng.Uninstaller.is_admin():
            self.btn_admin.setText("✓ 管理员")
            self.btn_admin.setStyleSheet("color:#3DDC97;border-color:rgba(61,220,151,0.4);")
            self.btn_admin.setEnabled(False)
        else:
            self.btn_admin.setText("以管理员重启")
            self.btn_admin.setEnabled(True)

    def _on_admin_click(self):
        if self._workers or self._closing:
            self.lbl_status.setText("请等待后台任务完成后重启")
            return
        if eng.Uninstaller.is_admin():
            return
        ok = eng.Uninstaller.relaunch_elevated()
        if ok:
            QTimer.singleShot(300, self.close)
        else:
            QMessageBox.warning(self, "提权失败", "无法启动管理员实例（UAC 被取消）。")

    # -------------------------------------------------------------- scan
    def start_scan(self):
        if self._busy or self._closing:
            return
        self._inventory_epoch += 1
        self._inventory_ready.clear()
        self._set_busy(True, "扫描已安装应用…")
        self.list.clear()
        self.lbl_count.setText("正在扫描…")
        self.empty_hint.hide()
        self._scan_worker = ScanWorker()
        self._scan_worker.progress.connect(lambda m: self.lbl_count.setText(m))
        self._scan_worker.done.connect(self._on_scanned)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._track_worker(self._scan_worker)
        self._scan_worker.start()

    def _on_scan_failed(self, msg):
        self._set_busy(False, "扫描失败")
        self.lbl_count.setText("扫描失败")
        self.log_line(f"✗ 扫描失败：{msg}")

    def _on_scanned(self, apps: list):
        self.apps = apps
        self._populate()
        self._set_busy(False, f"共 {len(apps)} 个应用")
        self.lbl_foot.setText(
            f"共 {len(apps)} 个可卸载应用 · "
            f"{'管理员权限' if eng.Uninstaller.is_admin() else '普通权限（受保护目录将跳过）'}")

    def _populate(self):
        self.list.clear()
        q = self.search.text().strip().lower()
        shown = 0
        for a in self.apps:
            if not self._match(a, q):
                continue
            it = QListWidgetItem()
            it.setData(Qt.UserRole, a)
            it.setSizeHint(QSize(380, 70))
            self.list.addItem(it)
            shown += 1
        self.lbl_count.setText(f"{shown} 个应用")
        self.empty_hint.setVisible(shown == 0)
        if shown:
            self.list.setCurrentRow(0)
        else:
            self._clear_detail()

    def _match(self, a: AppEntry, q: str) -> bool:
        if self._filter == "big" and (a.size or a.total_leftover) < 200 * 1024:
            if not (a.install_location and os.path.isdir(a.install_location)):
                return False
        if self._filter == "residue":
            risky = a.install_location or a.uninstall_type in ("nsis", "inno", "msiexec")
            if not risky:
                return False
        if self._filter == "store" and a.source != "store":
            return False
        if q:
            hay = f"{a.name} {a.publisher} {a.version}".lower()
            if q not in hay:
                return False
        return True

    def _set_filter(self, key: str):
        self._filter = key
        for k, b in self.pills.items():
            b.setChecked(k == key)
        self._populate()

    def _apply_filter(self):
        self._populate()

    # ---------------------------------------------------------- selection
    def _on_select(self, cur, prev):
        if not cur:
            self._clear_detail()
            return
        if self._closing:
            return
        entry: AppEntry = cur.data(Qt.UserRole)
        self.current = entry
        self._render_detail(entry)
        if entry.uid in self._inventory_ready:
            self._on_inventory(entry)
            return
        self.btn_go.setEnabled(False)
        self.btn_dry.setEnabled(False)
        self._inv_worker = InventoryWorker(entry)
        epoch = self._inventory_epoch
        self._inv_worker.done.connect(
            lambda result, generation=epoch: self._on_inventory(result)
            if generation == self._inventory_epoch else None)
        self._track_worker(self._inv_worker)
        self._inv_worker.start()

    def _clear_detail(self):
        self.current = None
        self.d_name.setText("选择一个应用")
        self.d_meta.setText("")
        self.d_icon.clear()
        self.d_sum.setText("")
        self._clear_lo_rows()
        self.btn_go.setEnabled(False)

    def _render_detail(self, e: AppEntry):
        self.d_icon.setPixmap(app_pixmap(e, 44))
        self.d_name.setText(e.name)
        meta = []
        if e.version:
            meta.append("v" + e.version)
        if e.publisher:
            meta.append(e.publisher)
        if e.source == "store":
            meta.append("商店应用")
        meta.append({"nsis": "NSIS 安装包", "inno": "Inno Setup", "msiexec": "MSI",
                     "appx": "MSIX 包", "winget": "winget 管理",
                     "custom": "自定义安装包"}.get(e.uninstall_type, e.uninstall_type))
        self.d_meta.setText(" · ".join(meta))
        self.d_sum.setText("正在清点残留…")
        self._clear_lo_rows()
        self.btn_go.setEnabled(True)

    def _clear_lo_rows(self):
        while self.lo_lay.count() > 1:
            it = self.lo_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _on_inventory(self, e: AppEntry):
        if self._closing or not self.current or e.uid != self.current.uid:
            return
        if e.uid in self._inventory_ready:
            e = self.current
        self._inventory_ready.add(e.uid)
        self.current = e
        self.btn_go.setEnabled(not self._busy)
        self.btn_dry.setEnabled(not self._busy)
        # replace stored entry so badge updates
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole).uid == e.uid:
                it.setData(Qt.UserRole, e)
                break
        self._clear_lo_rows()
        real = [i for i in e.leftovers if i.exists]
        total = sum(i.size for i in real)
        if not real:
            self.d_sum.setText("没有发现可清理的残留（卸载程序会完整处理）")
            self.lo_lay.insertWidget(0, _hint_label("官方卸载程序将自行清理，不额外删除文件"))
            return
        self.d_sum.setText(f"发现 {len(real)} 处残留 · 约 {human_size(total)}")
        for i, item in enumerate(real):
            self.lo_lay.insertWidget(i, self._leftover_row(item))

    def _leftover_row(self, item) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(2, 3, 2, 3)
        lay.setSpacing(9)
        cb = QCheckBox()
        cb.setChecked(False)
        cb.setEnabled(False)
        cb.setToolTip('此处仅作卸载前参考；卸载后在向导中重新扫描并选择。')
        lay.addWidget(cb, 0, Qt.AlignVCenter)
        kind = {"dir": "目录", "appxdata": "应用数据", "key": "注册表",
                "file": "文件", "service": "服务"}.get(item.kind, item.kind)
        name = QLabel((item.label if item.kind != "key" else item.path.split("\\")[-1])[:34])
        name.setStyleSheet("color:#DCE1EC;font-size:12px;")
        name.setToolTip(item.path)
        lay.addWidget(name, 1)
        note = QLabel(f"{kind} · {item.note}")
        note.setStyleSheet("color:#6E7689;font-size:11px;")
        lay.addWidget(note)
        if item.size:
            sz = QLabel(human_size(item.size))
            sz.setStyleSheet("color:#8A93A8;font-size:11px;")
            sz.setFixedWidth(74)
            sz.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(sz)
        return row

    def _toggle_item(self, item, state):
        item.checked = bool(state)

    # -------------------------------------------------------- uninstall
    def _start_uninstall(self, dry: bool):
        if (not self.current or self._busy or self._closing
                or self.current.uid not in self._inventory_ready):
            return
        e = self.current
        if not dry:
            from .wizard import UninstallWizard
            dialog = UninstallWizard(e, self)
            dialog.exec_()
            if dialog.operation_started:
                self._inventory_ready.clear()
                self.start_scan()
            return
        self.log.clear()
        self.log_line('演练：不会执行卸载或清理。')
        try:
            cmd = eng.Uninstaller(lambda _: None)._official_command(e)
            self.log_line('官方卸载命令：' + subprocess.list2cmdline(cmd))
        except Exception as exc:
            self.log_line('当前无法确定官方卸载命令：' + str(exc))
        self.log_line('官方卸载成功后重新扫描候选；届时须逐项审阅并确认。文件隔离，注册表只备份。')
        self.lbl_status.setText('演练完成，未执行任何操作')

    def _on_uninstall_done(self, rep: eng.Report):
        if self._closing:
            return
        self._set_busy(False)
        if rep.dry_run:
            title = "演练完成，未执行卸载或清理"
        elif not rep.official_ok:
            title = "官方卸载未成功确认；未执行残留清理"
        elif rep.clean:
            title = "卸载完成，已检查的位置无残留"
        else:
            title = "官方卸载完成；有保留项目或清理失败"
        self.lbl_status.setText(title)
        self.log_line(title)
        if rep.log_path:
            self.log_line(f"报告已保存：{rep.log_path}")
        box = QMessageBox(self)
        box.setWindowTitle("执行结果")
        box.setTextFormat(Qt.PlainText)
        box.setText(title)
        detail = [rep.official_detail]
        detail += [f"失败：{p} — {why}" for p, why in rep.failed]
        detail += [f"仍存在：{p}" for p in rep.remaining]
        detail += [f"按选择保留：{p}" for p in rep.retained]
        if rep.removed_bytes:
            detail.append(f"额外清理释放约 {human_size(rep.removed_bytes)}")
        box.setInformativeText("\n".join(detail[:12]))
        box.exec_()
        # Keep the selected snapshot after a dry run or failure so the user can
        # review exactly what was chosen. A successful real operation rescans.
        if rep.official_ok and not rep.dry_run:
            self._inventory_ready.clear()
            self.start_scan()

    def _track_worker(self, worker):
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._worker_finished(w))

    def _worker_finished(self, worker):
        self._workers.discard(worker)
        # References are released only after the native QThread has stopped.
        for attr in ("_scan_worker", "_inv_worker", "_uninst_worker"):
            if getattr(self, attr, None) is worker:
                setattr(self, attr, None)
        worker.deleteLater()
        if self._closing and not self._workers:
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if any(w.isRunning() for w in self._workers):
            self._closing = True
            self.setEnabled(False)
            self.lbl_status.setText("正在等待后台任务结束后关闭…")
            event.ignore()
            return
        event.accept()

    # ------------------------------------------------------------- misc
    def _set_busy(self, busy: bool, status: str = ""):
        self._busy = busy
        if status:
            self.lbl_status.setText(status)
        for w in (self.btn_go, self.btn_dry, self.btn_rescan):
            w.setEnabled(not busy)
        ready = bool(self.current and self.current.uid in self._inventory_ready)
        self.btn_go.setEnabled(not busy and ready)
        self.btn_dry.setEnabled(not busy and ready)
        for w in (self.list, self.search, self.cb_reg, self.cb_data, self.cb_link, self.lo_area):
            w.setEnabled(not busy)
        for w in self.pills.values():
            w.setEnabled(not busy)
        self.spinner.start() if busy else self.spinner.stop()
        if not busy:
            self.lbl_status.setStyleSheet("")

    def log_line(self, msg: str):
        self.log.appendPlainText(msg)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _open_recovery(self):
        if self._busy:
            return
        from .recovery_dialog import RecoveryDialog
        RecoveryDialog(self).exec_()

    def _open_logs(self):
        p = eng.LOG_DIR
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))  # type: ignore[attr-defined]


def _app_pixmap_local(e: AppEntry, size: int) -> QPixmap:
    return app_pixmap(e, size)


def _hint_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("color:#5E6577;font-size:11.5px;padding:6px 2px;")
    return l

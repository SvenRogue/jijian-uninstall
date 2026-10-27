"""主窗口：Apple 系统设置风格 —— 侧边栏应用列表 + 右侧分组卡片。

视觉规则：单一系统蓝强调色、发丝分隔线、分组圆角卡片、克制的字重层级。
功能与安全语义不变：主界面清点只作参考，真正清理在卸载向导内逐项确认。
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import (QSettings, QSize, Qt, QThread, QTimer, pyqtSignal)
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (QApplication, QCheckBox, QFrame, QGraphicsDropShadowEffect,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSizeGrip, QVBoxLayout, QWidget)

from . import chrome, engine as eng, scanner, theme
from .chrome import (Card, LogoWidget, SearchField, SegmentedControl, Spinner,
                     TrafficLights)
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


def _shadow(w, blur=30, dy=8, alpha=70):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(eff)
    return eff


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


# ------------------------------------------------------------------ window
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("极简卸载")
        self.setWindowIcon(QIcon(asset("jijian.ico")))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(980, 640)
        self.resize(1120, 740)

        self._drag_pos = None
        self.apps: list[AppEntry] = []
        self.current: AppEntry | None = None
        self._scan_worker = None
        self._inv_worker = None
        self._filter = "all"
        self._busy = False
        self._workers = set()
        self._closing = False
        self._inventory_ready = set()
        self._inventory_epoch = 0
        self._settings = QSettings("SvenRogue", "JiJianUninstall")

        theme.set_mode(self._settings.value("appearance", "light", type=str))
        self._build_ui()
        QTimer.singleShot(160, self.start_scan)

    # ---------------------------------------------------------------- shell
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.shell = QWidget()
        self.shell.setObjectName("Shell")
        outer.addWidget(self.shell)
        _shadow(self.shell, blur=44, dy=10, alpha=90)

        row = QHBoxLayout(self.shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())
        row.addWidget(self._build_content(), 1)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(318)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 14, 14, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(2, 0, 0, 0)
        lights = TrafficLights()
        lights.close_clicked.connect(self.close)
        lights.min_clicked.connect(self.showMinimized)
        lights.max_clicked.connect(self._toggle_max)
        top.addWidget(lights)
        top.addStretch(1)
        lay.addLayout(top)

        brand = QHBoxLayout()
        brand.setContentsMargins(2, 6, 0, 2)
        brand.setSpacing(9)
        brand.addWidget(LogoWidget(26))
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel("极简卸载")
        t.setProperty("role", "title")
        col.addWidget(t)
        sub = QLabel("卸载与残留审阅")
        sub.setProperty("role", "faint")
        col.addWidget(sub)
        brand.addLayout(col, 1)
        lay.addLayout(brand)

        self.search = SearchField("搜索应用、发布者")
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)

        self._seg = SegmentedControl((("all", "全部"), ("big", "大体积"),
                                      ("residue", "有残留"), ("store", "商店")))
        self._seg.changed.connect(self._set_filter)
        self.pills = self._seg._buttons
        lay.addWidget(self._seg)

        head = QHBoxLayout()
        head.setContentsMargins(3, 4, 3, 0)
        self.lbl_count = QLabel("正在扫描…")
        self.lbl_count.setProperty("role", "faint")
        head.addWidget(self.lbl_count)
        head.addStretch(1)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("AppList")
        self.list.setItemDelegate(AppDelegate())
        self.list.setSpacing(0)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.currentItemChanged.connect(self._on_select)
        lay.addWidget(self.list, 1)

        self.empty_hint = QLabel("没有匹配的应用")
        self.empty_hint.setProperty("role", "faint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.hide()
        lay.addWidget(self.empty_hint)

        lay.addWidget(self._sidebar_footer())
        return side

    def _sidebar_footer(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(2)

        self.btn_recovery = QPushButton("恢复中心")
        self.btn_recovery.setObjectName("SidebarItem")
        self.btn_recovery.setCursor(Qt.PointingHandCursor)
        self.btn_recovery.clicked.connect(self._open_recovery)
        lay.addWidget(self.btn_recovery)

        self.btn_open_logs = QPushButton("日志目录")
        self.btn_open_logs.setObjectName("SidebarItem")
        self.btn_open_logs.setCursor(Qt.PointingHandCursor)
        self.btn_open_logs.clicked.connect(self._open_logs)
        lay.addWidget(self.btn_open_logs)

        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        lay.addSpacing(5)
        lay.addWidget(line)
        lay.addSpacing(5)

        appr = QHBoxLayout()
        appr.setContentsMargins(2, 0, 0, 0)
        appr.setSpacing(8)
        label = QLabel("外观")
        label.setProperty("role", "faint")
        appr.addWidget(label)
        appr.addStretch(1)
        self._appearance = SegmentedControl((("light", "浅色"), ("dark", "深色")))
        self._appearance.set_value(theme.current_mode())
        self._appearance.changed.connect(self._set_appearance)
        appr.addWidget(self._appearance)
        lay.addLayout(appr)

        self.btn_admin = QPushButton("以管理员重启")
        self.btn_admin.setObjectName("Link")
        self.btn_admin.setCursor(Qt.PointingHandCursor)
        self.btn_admin.setToolTip("需要清理受保护目录时可重新以管理员身份启动")
        self.btn_admin.clicked.connect(self._on_admin_click)
        lay.addWidget(self.btn_admin)
        self._refresh_admin_badge()
        return wrap

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("Content")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(26, 18, 26, 12)
        lay.setSpacing(14)

        lay.addWidget(self._build_detail(), 1)

        log_card = self._build_log()
        log_card.setMaximumHeight(230)
        lay.addWidget(log_card)
        lay.addWidget(self._build_statusbar())
        return content

    def _build_detail(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(13)

        head = QHBoxLayout()
        head.setSpacing(14)
        self.d_icon = QLabel()
        self.d_icon.setFixedSize(52, 52)
        head.addWidget(self.d_icon, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.d_name = QLabel("选择一个应用")
        self.d_name.setProperty("role", "h1")
        self.d_name.setWordWrap(False)
        col.addWidget(self.d_name)
        self.d_meta = QLabel("从左侧选择要卸载的应用")
        self.d_meta.setProperty("role", "meta")
        col.addWidget(self.d_meta)
        head.addLayout(col, 1)

        self.btn_dry = QPushButton("演练")
        self.btn_dry.setObjectName("Secondary")
        self.btn_dry.setCursor(Qt.PointingHandCursor)
        self.btn_dry.setToolTip("只显示将要执行的操作，不做任何修改")
        self.btn_dry.clicked.connect(lambda: self._start_uninstall(dry=True))
        head.addWidget(self.btn_dry, 0, Qt.AlignTop)

        self.btn_go = QPushButton("卸载向导")
        self.btn_go.setObjectName("Primary")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.setEnabled(False)
        self.btn_go.clicked.connect(lambda: self._start_uninstall(dry=False))
        head.addWidget(self.btn_go, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.d_sum = QLabel("")
        self.d_sum.setProperty("role", "sub")
        lay.addWidget(self.d_sum)

        preview = Card("残留预览")
        self.lo_area = QScrollArea()
        self.lo_area.setWidgetResizable(True)
        self.lo_area.setFrameShape(QFrame.NoFrame)
        self.lo_area.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.lo_area.setMinimumHeight(150)
        self.lo_host = QWidget()
        self.lo_host.setObjectName("ScrollBody")
        self.lo_lay = QVBoxLayout(self.lo_host)
        self.lo_lay.setContentsMargins(0, 0, 0, 0)
        self.lo_lay.setSpacing(0)
        self.lo_lay.addStretch(1)
        self.lo_area.setWidget(self.lo_host)
        preview.body.addWidget(self.lo_area)
        lay.addWidget(preview, 1)

        # kept for compatibility with the pre-wizard layout / tests
        self.cb_reg = QCheckBox("注册表")
        self.cb_data = QCheckBox("数据与缓存")
        self.cb_link = QCheckBox("快捷方式")
        for cb in (self.cb_reg, self.cb_data, self.cb_link):
            cb.setChecked(False)
            cb.hide()
        return wrap

    def _build_log(self) -> QWidget:
        card = Card("执行日志")
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(10, 9, 10, 10)
        lay.setSpacing(7)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(1, 0, 1, 0)
        hdr.setSpacing(7)
        self.spinner = Spinner()
        self.spinner.hide()
        hdr.addWidget(self.spinner)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setProperty("role", "faint")
        hdr.addWidget(self.lbl_status)
        hdr.addStretch(1)
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
        self.progress.setFixedHeight(4)
        lay.addWidget(self.progress)

        card.body.addWidget(wrap)
        return card

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(2, 0, 0, 0)
        lay.setSpacing(8)
        self.lbl_foot = QLabel("")
        self.lbl_foot.setProperty("role", "faint")
        lay.addWidget(self.lbl_foot)
        lay.addStretch(1)
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

    def mousePressEvent(self, e):
        # the sidebar/title area is draggable like a native window
        if e.button() == Qt.LeftButton and e.pos().y() < 56 and e.pos().x() < 318:
            self._tb_press(e)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        self._tb_move(e)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._tb_release(e)
        super().mouseReleaseEvent(e)

    # ------------------------------------------------------------ appearance
    def _set_appearance(self, mode: str):
        theme.set_mode(mode)
        self._settings.setValue("appearance", mode)
        app = QApplication.instance()
        if app:
            theme.apply_palette(app, mode)
        self.update()

    # ------------------------------------------------------------ admin
    def _refresh_admin_badge(self):
        if eng.Uninstaller.is_admin():
            self.btn_admin.setText("管理员权限")
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
        self._set_busy(True, "正在扫描已安装应用…")
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
        self.log_line(f"扫描失败：{msg}")

    def _on_scanned(self, apps: list):
        self.apps = apps
        self._populate()
        self._set_busy(False, f"共 {len(apps)} 个应用")
        self.lbl_foot.setText(
            f"{len(apps)} 个可卸载应用 · "
            f"{'管理员权限' if eng.Uninstaller.is_admin() else '普通权限，受保护目录将跳过'}")

    def _populate(self):
        self.list.clear()
        q = self.search.text().strip().lower()
        shown = 0
        for a in self.apps:
            if not self._match(a, q):
                continue
            it = QListWidgetItem()
            it.setData(Qt.UserRole, a)
            it.setSizeHint(QSize(280, 52))
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
        self._seg.set_value(key)
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
        self.d_meta.setText("从左侧选择要卸载的应用")
        self.d_icon.clear()
        self.d_sum.setText("")
        self._clear_lo_rows()
        self.btn_go.setEnabled(False)
        self.btn_dry.setEnabled(False)

    def _render_detail(self, e: AppEntry):
        self.d_icon.setPixmap(app_pixmap(e, 52))
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
        self.d_meta.setText("  ·  ".join(meta))
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
            self.d_sum.setText("没有发现可清理的残留，卸载程序会完整处理")
            self.lo_lay.insertWidget(0, _hint_label("官方卸载程序将自行清理，不额外删除文件"))
            return
        self.d_sum.setText(f"发现 {len(real)} 处残留 · 约 {human_size(total)} · 卸载后重新扫描确认")
        for i, item in enumerate(real):
            self.lo_lay.insertWidget(i, self._leftover_row(item, last=(i == len(real) - 1)))

    def _leftover_row(self, item, last: bool = False) -> QWidget:
        row = QFrame()
        row.setObjectName("CardRow")
        row.setProperty("last", "true" if last else "false")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        dot = QLabel("•")
        dot.setStyleSheet("color:#8E8E93;font-size:12px;")
        lay.addWidget(dot, 0, Qt.AlignVCenter)
        kind = {"dir": "目录", "appxdata": "应用数据", "key": "注册表",
                "file": "文件", "service": "服务"}.get(item.kind, item.kind)
        name = QLabel(item.label if item.kind != "key" else item.path.split("\\")[-1])
        name.setProperty("role", "rowname")
        name.setToolTip(item.path)
        lay.addWidget(name, 1)
        note = QLabel(f"{kind} · {item.note}")
        note.setProperty("role", "rownote")
        lay.addWidget(note)
        if item.size:
            sz = QLabel(human_size(item.size))
            sz.setProperty("role", "size")
            sz.setFixedWidth(66)
            sz.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(sz)
        return row

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
        self.log_line("演练：不会执行卸载或清理。")
        try:
            cmd = eng.Uninstaller(lambda _: None)._official_command(e)
            self.log_line("官方卸载命令：" + subprocess.list2cmdline(cmd))
        except Exception as exc:
            self.log_line("当前无法确定官方卸载命令：" + str(exc))
        self.log_line("官方卸载成功后重新扫描候选；届时须逐项审阅并确认。文件隔离，注册表只备份。")
        self.lbl_status.setText("演练完成，未执行任何操作")

    def _track_worker(self, worker):
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._worker_finished(w))

    def _worker_finished(self, worker):
        self._workers.discard(worker)
        for attr in ("_scan_worker", "_inv_worker"):
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
        for w in (self.btn_go, self.btn_dry):
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


def _hint_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setProperty("role", "faint")
    l.setContentsMargins(12, 8, 12, 8)
    return l

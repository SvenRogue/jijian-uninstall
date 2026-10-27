"""Guided vendor uninstall -> residual review -> recoverable cleanup UI.

Visual language: Apple system-settings style, driven entirely by ``theme``.
Behaviour, signals and public attributes are unchanged.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog,
                             QHBoxLayout, QHeaderView,
                             QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
                             QPushButton, QStackedWidget, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from . import leftovers, scanner, theme
from .workflow import UninstallWorkflow


class Work(QThread):
    done = pyqtSignal(object)
    error = pyqtSignal(str)
    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:
            self.error.emit(f'{type(exc).__name__}: {exc}')


# ------------------------------------------------------------------ styling
def _tint(color: str, alpha: float) -> str:
    """'#FF9500' -> 'rgba(255,149,0,0.12)' for soft, theme-derived fills."""
    value = (color or "").lstrip("#")
    if len(value) != 6:
        return color
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return color
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _repolish(widget) -> None:
    """Re-evaluate property selectors after an ``active``/``role`` change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class ShellDialog(QDialog):
    """Themed dialog with native window controls, shared by both dialogs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None
        self._tinted: list[tuple[QLabel, str, float]] = []

    # ------------------------------------------------------------- shell
    def _init_shell(self, caption: str, minimum, default) -> QVBoxLayout:
        self.setObjectName("DialogRoot")
        self.setWindowTitle(caption)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
                            Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint |
                            Qt.WindowCloseButtonHint)
        self.setMinimumSize(*minimum)
        self.resize(*default)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.shell = QWidget()
        self.shell.setObjectName("DialogShell")
        outer.addWidget(self.shell)

        root = QVBoxLayout(self.shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(26, 20, 26, 20)
        self._body.setSpacing(14)
        root.addWidget(body, 1)
        return self._body

    # ------------------------------------------------------------- window
    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _drag_move(self, event):
        if self._drag_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        if self.isMaximized():
            self.showNormal()
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        self.move(event.globalPos() - self._drag_pos)

    # ------------------------------------------------------------- theme
    # Keep Qt's default header palette from painting a light band in dark mode.
    _EXTRA_QSS = """
QHeaderView { background: transparent; }
QHeaderView::section { background: transparent; }
QTreeWidget::branch { background: transparent; }
QTreeWidget QScrollBar:vertical, QTreeWidget QScrollBar:horizontal { background: transparent; }
"""

    def _restyle(self):
        self.setStyleSheet(theme.dialog_qss() + self._EXTRA_QSS)
        self._style_tints()

    def _style_tints(self):
        c = theme.palette()
        for label, key, alpha in self._tinted:
            fill = _tint(c[key], alpha)
            edge = _tint(c[key], min(1.0, alpha + 0.16))
            label.setStyleSheet(
                "QLabel {"
                f"background: {fill}; border: 1px solid {edge}; border-radius: 9px;"
                f"padding: 11px 13px; color: {c['text']}; font-size: 12px;"
                "}")

    def _banner(self, text: str, key: str = "warn", alpha: float = 0.12) -> QLabel:
        """Soft tinted rounded notice, recoloured from the live palette."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("role", "meta")
        self._tinted.append((label, key, alpha))
        return label

    def showEvent(self, event):
        self._restyle()
        super().showEvent(event)


# ------------------------------------------------------------------ wizard
class UninstallWizard(ShellDialog):
    logline = pyqtSignal(str)
    progressed = pyqtSignal(int)
    result_ready = pyqtSignal(object)

    def __init__(self, entry, parent=None, workflow=None):
        super().__init__(parent)
        self.entry = copy.deepcopy(entry)
        self.workflow = workflow or UninstallWorkflow(self.entry, self.logline.emit, self.progressed.emit)
        self._workers = set()
        self._busy = False
        self._operation = False
        self.candidates = None
        self.report = None
        self.rows = []
        self.steps = []
        self._build()
        self._set_phase(0)
        self._restyle()
        self.logline.connect(self._log)
        self.progressed.connect(lambda n: self.progress.setValue(n))

    @property
    def operation_started(self):
        return self._operation

    def _build(self):
        layout = self._init_shell('卸载向导', (940, 710), (1080, 780))

        title = QLabel(self.entry.name)
        title.setProperty('role', 'h1')
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel('官方卸载 → 重新扫描 → 审阅并隔离。每一步的结果都能看见。')
        subtitle.setProperty('role', 'meta')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        steps = QHBoxLayout()
        steps.setSpacing(8)
        for text in ('01  官方卸载', '02  审阅残留', '03  处理结果'):
            lab = QLabel(text)
            lab.setObjectName('Step')
            lab.setProperty('active', 'false')
            steps.addWidget(lab, 1)
            self.steps.append(lab)
        layout.addLayout(steps)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)

        # ---------------------------------------------------------- prepare
        prepare = QWidget()
        p = QVBoxLayout(prepare)
        p.setContentsMargins(0, 10, 0, 0)
        p.setSpacing(16)

        intro = QLabel('先使用应用自己的卸载程序')
        intro.setProperty('role', 'h2')
        p.addWidget(intro)

        note = QLabel('接下来可能出现厂商卸载窗口。请先保存应用内工作，并在厂商窗口完成卸载。\n'
                      '只有确认官方卸载完成，才会进入额外残留扫描。')
        note.setWordWrap(True)
        note.setProperty('role', 'meta')
        p.addWidget(note)

        modes = QHBoxLayout()
        modes.setSpacing(10)
        mode_label = QLabel('卸载后扫描范围')
        mode_label.setProperty('role', 'meta')
        modes.addWidget(mode_label)
        self.mode = QComboBox()
        for key, (name, desc) in leftovers.PROFILES.items():
            self.mode.addItem(name, key)
        self.mode.setCurrentIndex(1)
        modes.addWidget(self.mode)
        modes.addStretch(1)
        p.addLayout(modes)

        self.mode_note = QLabel()
        self.mode_note.setWordWrap(True)
        self.mode_note.setProperty('role', 'faint')
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()
        p.addWidget(self.mode_note)

        self._warn = self._banner('额外清理默认不选中任何项目。厂商卸载器可能按自身规则删除安装文件或设置。')
        p.addWidget(self._warn)

        p.addStretch()
        self.pages.addWidget(prepare)

        # ----------------------------------------------------------- review
        review = QWidget()
        r = QVBoxLayout(review)
        r.setContentsMargins(0, 4, 0, 0)
        r.setSpacing(10)

        self.review_summary = QLabel()
        self.review_summary.setWordWrap(True)
        self.review_summary.setProperty('role', 'meta')
        r.addWidget(self.review_summary)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_all = QPushButton('选择全部候选')
        self.btn_all.setObjectName('Secondary')
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        actions.addWidget(self.btn_all)
        self.btn_none = QPushButton('取消全选')
        self.btn_none.setObjectName('Secondary')
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        actions.addWidget(self.btn_none)
        self.btn_copy = QPushButton('复制完整位置')
        self.btn_copy.setObjectName('Secondary')
        self.btn_copy.clicked.connect(self._copy_path)
        actions.addWidget(self.btn_copy)
        actions.addStretch(1)
        self.selected_label = QLabel('未选择项目')
        self.selected_label.setProperty('role', 'faint')
        actions.addWidget(self.selected_label)
        r.addLayout(actions)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['位置 / 项目', '大小', '匹配依据', '核对等级'])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 88)
        self.tree.setColumnWidth(2, 230)
        self.tree.setColumnWidth(3, 96)
        self.tree.itemChanged.connect(self._selection_changed)
        r.addWidget(self.tree, 1)

        hint = QLabel('文件和目录移入隔离区，仍占磁盘空间，可从恢复中心还原；注册表仅导出备份，原项保留。'
                      '跨磁盘、单项超过 2 GiB、包含链接或权限不足时保留原文件。')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        hint.setProperty('role', 'faint')
        r.addWidget(hint)
        self.pages.addWidget(review)

        # --------------------------------------------------------- complete
        complete = QWidget()
        c = QVBoxLayout(complete)
        c.setContentsMargins(0, 14, 0, 0)
        c.setSpacing(14)

        self.result_title = QLabel()
        self.result_title.setProperty('role', 'h1')
        self.result_title.setWordWrap(True)
        c.addWidget(self.result_title)

        self.result_text = QLabel()
        self.result_text.setWordWrap(True)
        self.result_text.setProperty('role', 'meta')
        c.addWidget(self.result_text)

        c.addStretch()
        self.btn_export = QPushButton('导出本次报告…')
        self.btn_export.setObjectName('Secondary')
        self.btn_export.clicked.connect(self._export_report)
        c.addWidget(self.btn_export, 0, Qt.AlignLeft)
        self.pages.addWidget(complete)

        # ----------------------------------------------- log, progress, actions
        self.log = QPlainTextEdit()
        self.log.setObjectName('Log')
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2500)
        self.log.setFixedHeight(118)
        layout.addWidget(self.log)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        layout.addWidget(self.progress)

        bottom = QHBoxLayout()
        bottom.setSpacing(9)
        self.status = QLabel('准备就绪')
        self.status.setProperty('role', 'faint')
        bottom.addWidget(self.status, 1)
        self.btn_secondary = QPushButton('取消')
        self.btn_secondary.setObjectName('Secondary')
        self.btn_secondary.clicked.connect(self._secondary)
        bottom.addWidget(self.btn_secondary)
        self.btn_primary = QPushButton('开始官方卸载')
        self.btn_primary.setObjectName('Primary')
        self.btn_primary.clicked.connect(self._primary)
        bottom.addWidget(self.btn_primary)
        layout.addLayout(bottom)

    def _restyle(self):
        super()._restyle()
        for label in self.steps:
            _repolish(label)

    def _mode_changed(self):
        mode = self.mode.currentData()
        self.mode_note.setText(leftovers.PROFILES[mode][1])

    def _set_phase(self, index):
        self.pages.setCurrentIndex(index)
        for i, label in enumerate(self.steps):
            label.setProperty('active', 'true' if i == index else 'false')
            _repolish(label)
        if index == 0:
            self.btn_primary.setText('开始官方卸载'); self.btn_secondary.setText('取消')
        elif index == 1:
            self.btn_primary.setText('备份并隔离选中项'); self.btn_secondary.setText('保留全部并完成')
            self._selection_changed()
        else:
            self.btn_primary.setText('完成'); self.btn_secondary.setText('恢复中心')

    def _run(self, fn, callback, message):
        self._busy = True
        self.status.setText(message)
        self.btn_primary.setEnabled(False)
        self.btn_secondary.setEnabled(False)
        self.mode.setEnabled(False)
        self.tree.setEnabled(False)
        for b in (self.btn_all, self.btn_none, self.btn_copy):
            b.setEnabled(False)
        worker = Work(fn, self)
        self._workers.add(worker)
        worker.done.connect(lambda result: self._result(result, callback))
        worker.error.connect(self._error)
        worker.finished.connect(lambda: self._worker_finished(worker))
        worker.start()

    def _worker_finished(self, worker):
        self._workers.discard(worker)
        worker.deleteLater()

    def _result(self, result, callback):
        self._busy = False
        self.btn_primary.setEnabled(True)
        self.btn_secondary.setEnabled(True)
        self.tree.setEnabled(True)
        for b in (self.btn_all, self.btn_none, self.btn_copy):
            b.setEnabled(True)
        callback(result)

    def _error(self, text):
        self._busy = False
        self.status.setText('操作停止，详情见日志')
        self._log('操作停止：' + text)
        self.btn_secondary.setEnabled(True)
        if self.workflow.phase == 'review':
            self.btn_primary.setEnabled(True)
            self.tree.setEnabled(True)
            for b in (self.btn_all, self.btn_none, self.btn_copy):
                b.setEnabled(True)
        else:
            self.btn_primary.setEnabled(False)
            self.btn_secondary.setText('关闭')

    def _primary(self):
        if self._busy: return
        page = self.pages.currentIndex()
        if page == 0:
            answer = QMessageBox.question(self, '确认官方卸载', f'即将卸载“{self.entry.name}”。\n请先保存工作。完成后仍需单独审阅额外清理项。', QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes: return
            self._operation = True; self._set_phase(0)
            self._run(lambda: self.workflow.uninstall(), self._official_done, '等待厂商卸载程序完成…')
        elif page == 1:
            chosen = sum(item.checkState(0) == Qt.Checked for item, _ in self.rows)
            if not chosen: return
            answer = QMessageBox.question(self, '确认本次额外清理', f'处理明确选中的 {chosen} 项？\n文件移入隔离区；注册表仅导出备份并保留原项。未选中项保留。', QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes: return
            reviewed = self._reviewed()
            self._run(lambda: self.workflow.cleanup(reviewed), self._cleanup_done, '正在备份和隔离选中项…')
        else:
            self.accept()

    def _official_done(self, rep):
        self.report = rep
        if not rep.official_ok:
            self._show_result(rep, '官方卸载未完成', '未执行任何额外清理。可关闭后检查厂商卸载窗口或重启要求。\n' + rep.official_detail)
            return
        mode = self.mode.currentData()
        self._run(lambda: self.workflow.scan(mode), self._scan_done, '官方卸载已完成，正在重新扫描残留…')

    def _scan_done(self, entry):
        self.candidates = entry
        self.tree.blockSignals(True)
        self.tree.clear()
        self.rows = []
        groups = {}
        for item in entry.leftovers:
            group = '注册表（只导出，不删除）' if item.kind == 'key' else ('快捷方式' if item.kind == 'file' else '文件 / 数据目录（隔离）')
            if group not in groups:
                top = QTreeWidgetItem([group])
                self.tree.addTopLevelItem(top)
                groups[group] = top
            row = QTreeWidgetItem([item.path, scanner.human_size(item.size), item.basis, item.confidence])
            row.setToolTip(0, item.path)
            row.setToolTip(2, item.basis)
            row.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            if item.selectable:
                row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
                row.setCheckState(0, Qt.Unchecked)
            else:
                row.setFlags(row.flags() & ~Qt.ItemIsEnabled)
                row.setText(3, '不可隔离')
            row.setData(0, Qt.UserRole, item.path)
            groups[group].addChild(row)
            self.rows.append((row, item))
        self.tree.expandAll()
        self.tree.blockSignals(False)
        total = sum(i.size for i in entry.leftovers)
        self.review_summary.setText(f'官方卸载已完成 · {leftovers.PROFILES[self.mode.currentData()][0]}扫描发现 {len(entry.leftovers)} 项候选，约 {scanner.human_size(total)}。请核对完整位置后选择。')
        self.status.setText('等待你审阅；当前没有选中任何项目')
        self._set_phase(1)

    def _selection_changed(self, *args):
        chosen = [item for row, item in self.rows if row.checkState(0) == Qt.Checked]
        self.selected_label.setText(f'已选择 {len(chosen)} 项 · {scanner.human_size(sum(i.size for i in chosen))}')
        if self.pages.currentIndex() == 1:
            self.btn_primary.setEnabled(bool(chosen) and not self._busy)

    def _check_all(self, checked):
        if self._busy: return
        for row, item in self.rows:
            if item.selectable:
                row.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def _copy_path(self):
        row = self.tree.currentItem()
        if row and row.data(0, Qt.UserRole):
            QApplication.clipboard().setText(row.data(0, Qt.UserRole))

    def _reviewed(self):
        reviewed = copy.deepcopy(self.candidates)
        selected = {leftovers.identity(item) for row, item in self.rows if row.checkState(0) == Qt.Checked}
        for item in reviewed.leftovers:
            item.checked = leftovers.identity(item) in selected
        return reviewed

    def _secondary(self):
        if self._busy: return
        if self.pages.currentIndex() == 1:
            self._run(self.workflow.finish_without_cleanup, self._cleanup_done, '保存保留全部的处理结果…')
        elif self.pages.currentIndex() == 2:
            from .recovery_dialog import RecoveryDialog
            RecoveryDialog(self).exec_()
        else:
            self.reject()

    def _cleanup_done(self, rep):
        self.report = rep
        title = '已完成本次处理' if not rep.failed else '部分项目已保留'
        text = (f'{len(rep.removed)} 项已处理，{len(rep.retained)} 项按选择保留，{len(rep.failed)} 项未能处理。\n'
                f'隔离数据约 {scanner.human_size(rep.quarantined_bytes)}，仍占磁盘空间。\n'
                '可恢复范围仅限本工具的隔离文件和注册表导出；无法撤销厂商卸载器本身。')
        if rep.recovery_session:
            text += '\n恢复记录：' + rep.recovery_session[:12]
        self._show_result(rep, title, text)

    def _show_result(self, rep, title, text):
        self.result_title.setText(title)
        self.result_text.setText(text)
        self._set_phase(2)
        self.status.setText('处理结果已保存；可导出报告')
        self.btn_primary.setEnabled(True)
        self.btn_secondary.setEnabled(True)
        self.result_ready.emit(rep)

    def _log(self, text):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _export_report(self):
        if not self.report: return
        target, _ = QFileDialog.getSaveFileName(self, '导出处理报告', '卸载报告.json', 'JSON (*.json)')
        if not target: return
        try:
            from dataclasses import asdict
            Path(target).write_text(json.dumps(asdict(self.report), ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, '导出失败', str(exc))

    def reject(self):
        if self._busy or any(w.isRunning() for w in self._workers):
            self.status.setText('当前任务仍在运行，请等待完成；不会强制中断卸载器。'); return
        super().reject()

    def closeEvent(self, event):
        if self._busy or any(w.isRunning() for w in self._workers):
            self.status.setText('当前任务仍在运行，请等待完成。'); event.ignore(); return
        event.accept()

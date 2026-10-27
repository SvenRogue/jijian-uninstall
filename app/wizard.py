"""Guided vendor uninstall -> residual review -> recoverable cleanup UI."""
from __future__ import annotations
import copy
import json
import os
import shutil
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QHeaderView)
from . import leftovers, scanner
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


DIALOG_STYLE = '''
QDialog { background:#11151e; color:#e8edf7; }
QLabel { color:#dce4f4; }
QLabel#Muted {color:#96a4bd;font-size:12px;}
QLabel#Heading {font-size:24px;font-weight:600;}
QLabel#Step {font-size:12px;padding:9px 12px;background:#1a2231;border-radius:8px;}
QPushButton {background:#25324b;color:#eaf0ff;border:1px solid #384c70;border-radius:8px;padding:9px 17px;}
QPushButton:hover {background:#354767;}
QPushButton:disabled {color:#66738a;background:#1b2230;border-color:#273146;}
QPushButton#Primary {background:#6485f4;border:0;color:white;font-weight:600;}
QPushButton#Primary:disabled {background:#303d60;color:#7d8caf;}
QComboBox {background:#1c2639;color:#e7eeff;border:1px solid #354766;border-radius:6px;padding:7px;min-width:100px;}
QComboBox QAbstractItemView {background:#202b40;color:#eaf0ff;selection-background-color:#435d9d;}
QTreeWidget {background:#151d2a;color:#e6edfa;border:1px solid #2c394f;border-radius:8px;alternate-background-color:#192333;}
QTreeWidget::item {padding:5px;}
QTreeWidget::item:selected {background:#2b426c;}
QTreeWidget::indicator {width:17px;height:17px;}
QHeaderView::section {background:#1d293b;color:#98add0;border:0;padding:9px;}
QPlainTextEdit {background:#0c111a;color:#98accb;border:1px solid #27364c;border-radius:8px;padding:8px;font-family:Consolas;font-size:12px;}
QProgressBar {background:#263249;border:0;height:5px;border-radius:2px;}
QProgressBar::chunk {background:#79a0ff;border-radius:2px;}
'''


class UninstallWizard(QDialog):
    logline = pyqtSignal(str)
    progressed = pyqtSignal(int)
    result_ready = pyqtSignal(object)
    def __init__(self, entry, parent=None, workflow=None):
        super().__init__(parent)
        self.setWindowTitle('卸载向导 · 极简卸载')
        self.setMinimumSize(940, 710)
        self.resize(1080, 780)
        self.setStyleSheet(DIALOG_STYLE)
        self.entry = copy.deepcopy(entry)
        self.workflow = workflow or UninstallWorkflow(self.entry, self.logline.emit, self.progressed.emit)
        self._workers = set()
        self._busy = False
        self._operation = False
        self.candidates = None
        self.report = None
        self.rows = []
        self.logline.connect(self._log)
        self.progressed.connect(lambda n: self.progress.setValue(n))
        self._build()
        self._set_phase(0)

    @property
    def operation_started(self):
        return self._operation

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
        title = QLabel(self.entry.name); title.setObjectName('Heading')
        title.setWordWrap(True); layout.addWidget(title)
        subtitle = QLabel('官方卸载 → 重新扫描 → 审阅并隔离。每一步的结果都能看见。')
        subtitle.setObjectName('Muted'); layout.addWidget(subtitle)
        steps = QHBoxLayout()
        self.steps=[]
        for text in ('01  官方卸载', '02  审阅残留', '03  处理结果'):
            lab=QLabel(text); lab.setObjectName('Step'); steps.addWidget(lab); self.steps.append(lab)
        layout.addLayout(steps)
        self.pages=QStackedWidget(); layout.addWidget(self.pages,1)
        # Prepare page
        prepare=QWidget(); p=QVBoxLayout(prepare); p.setContentsMargins(0,14,0,0); p.setSpacing(16)
        intro=QLabel('先使用应用自己的卸载程序'); intro.setStyleSheet('font-size:19px;font-weight:600;'); p.addWidget(intro)
        note=QLabel('接下来可能出现厂商卸载窗口。请先保存应用内工作，并在厂商窗口完成卸载。\n只有确认官方卸载完成，才会进入额外残留扫描。')
        note.setWordWrap(True); note.setObjectName('Muted'); p.addWidget(note)
        self.mode=QComboBox()
        for key,(name,desc) in leftovers.PROFILES.items():
            self.mode.addItem(name,key)
        self.mode.setCurrentIndex(1)
        modes=QHBoxLayout(); modes.addWidget(QLabel('卸载后扫描范围')); modes.addWidget(self.mode); modes.addStretch(); p.addLayout(modes)
        self.mode_note=QLabel(); self.mode_note.setWordWrap(True); self.mode_note.setObjectName('Muted')
        self.mode.currentIndexChanged.connect(self._mode_changed); self._mode_changed(); p.addWidget(self.mode_note)
        warn=QLabel('额外清理默认不选中任何项目。厂商卸载器可能按自身规则删除安装文件或设置。')
        warn.setWordWrap(True); warn.setStyleSheet('color:#d4b580;background:#29251f;padding:12px;border-radius:8px;'); p.addWidget(warn)
        p.addStretch(); self.pages.addWidget(prepare)
        # Review page
        review=QWidget(); r=QVBoxLayout(review); r.setContentsMargins(0,4,0,0); r.setSpacing(10)
        self.review_summary=QLabel(); self.review_summary.setWordWrap(True); r.addWidget(self.review_summary)
        actions=QHBoxLayout()
        self.btn_all=QPushButton('选择全部候选'); self.btn_all.clicked.connect(lambda:self._check_all(True)); actions.addWidget(self.btn_all)
        self.btn_none=QPushButton('取消全选'); self.btn_none.clicked.connect(lambda:self._check_all(False)); actions.addWidget(self.btn_none)
        self.btn_copy=QPushButton('复制完整位置'); self.btn_copy.clicked.connect(self._copy_path); actions.addWidget(self.btn_copy)
        actions.addStretch(); self.selected_label=QLabel('未选择项目'); actions.addWidget(self.selected_label); r.addLayout(actions)
        self.tree=QTreeWidget(); self.tree.setHeaderLabels(['位置 / 项目','大小','匹配依据','核对等级']); self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True); self.tree.setColumnWidth(0,450); self.tree.setColumnWidth(1,90); self.tree.setColumnWidth(2,240)
        self.tree.header().setSectionResizeMode(0,QHeaderView.Interactive)
        self.tree.itemChanged.connect(self._selection_changed); r.addWidget(self.tree,1)
        hint=QLabel('文件和目录移入隔离区，仍占磁盘空间，可从恢复中心还原；注册表仅导出备份，原项保留。跨磁盘、单项超过 2 GiB、包含链接或权限不足时保留原文件。')
        hint.setObjectName('Muted'); hint.setWordWrap(True); r.addWidget(hint)
        self.pages.addWidget(review)
        # Complete page
        complete=QWidget(); c=QVBoxLayout(complete); c.setContentsMargins(0,18,0,0); c.setSpacing(14)
        self.result_title=QLabel(); self.result_title.setStyleSheet('font-size:23px;font-weight:600;'); c.addWidget(self.result_title)
        self.result_text=QLabel(); self.result_text.setWordWrap(True); self.result_text.setObjectName('Muted'); c.addWidget(self.result_text)
        c.addStretch(); self.btn_export=QPushButton('导出本次报告…'); self.btn_export.clicked.connect(self._export_report); c.addWidget(self.btn_export,0,Qt.AlignLeft)
        self.pages.addWidget(complete)
        # Log and actions remain visible throughout.
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(2500); self.log.setFixedHeight(130); layout.addWidget(self.log)
        self.progress=QProgressBar(); self.progress.setRange(0,100); self.progress.setTextVisible(False); self.progress.setFixedHeight(5); layout.addWidget(self.progress)
        bottom=QHBoxLayout(); self.status=QLabel('准备就绪'); self.status.setObjectName('Muted'); bottom.addWidget(self.status,1)
        self.btn_secondary=QPushButton('取消'); self.btn_secondary.clicked.connect(self._secondary); bottom.addWidget(self.btn_secondary)
        self.btn_primary=QPushButton('开始官方卸载'); self.btn_primary.setObjectName('Primary'); self.btn_primary.clicked.connect(self._primary); bottom.addWidget(self.btn_primary)
        layout.addLayout(bottom)

    def _mode_changed(self):
        mode=self.mode.currentData()
        self.mode_note.setText(leftovers.PROFILES[mode][1])

    def _set_phase(self,index):
        self.pages.setCurrentIndex(index)
        for i,label in enumerate(self.steps):
            label.setStyleSheet('background:#2f4876;color:#c6d9ff;' if i==index else 'background:#1a2231;color:#70839f;')
        if index==0:
            self.btn_primary.setText('开始官方卸载'); self.btn_secondary.setText('取消')
        elif index==1:
            self.btn_primary.setText('备份并隔离选中项'); self.btn_secondary.setText('保留全部并完成')
            self._selection_changed()
        else:
            self.btn_primary.setText('完成'); self.btn_secondary.setText('恢复中心')

    def _run(self,fn,callback,message):
        self._busy=True; self.status.setText(message)
        self.btn_primary.setEnabled(False); self.btn_secondary.setEnabled(False); self.mode.setEnabled(False)
        self.tree.setEnabled(False)
        for b in (self.btn_all,self.btn_none,self.btn_copy): b.setEnabled(False)
        worker=Work(fn,self); self._workers.add(worker)
        worker.done.connect(lambda result:self._result(result,callback))
        worker.error.connect(self._error)
        worker.finished.connect(lambda:self._worker_finished(worker))
        worker.start()

    def _worker_finished(self,worker):
        self._workers.discard(worker); worker.deleteLater()

    def _result(self,result,callback):
        self._busy=False
        self.btn_primary.setEnabled(True); self.btn_secondary.setEnabled(True); self.tree.setEnabled(True)
        for b in (self.btn_all,self.btn_none,self.btn_copy): b.setEnabled(True)
        callback(result)

    def _error(self,text):
        self._busy=False; self.status.setText('操作停止，详情见日志')
        self._log('操作停止：'+text); self.btn_secondary.setEnabled(True)
        if self.workflow.phase=='review':
            self.btn_primary.setEnabled(True); self.tree.setEnabled(True)
            for b in (self.btn_all,self.btn_none,self.btn_copy): b.setEnabled(True)
        else:
            self.btn_primary.setEnabled(False); self.btn_secondary.setText('关闭')

    def _primary(self):
        if self._busy: return
        page=self.pages.currentIndex()
        if page==0:
            answer=QMessageBox.question(self,'确认官方卸载',f'即将卸载“{self.entry.name}”。\n请先保存工作。完成后仍需单独审阅额外清理项。',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if answer!=QMessageBox.Yes: return
            self._operation=True; self._set_phase(0)
            self._run(lambda:self.workflow.uninstall(),self._official_done,'等待厂商卸载程序完成…')
        elif page==1:
            chosen=sum(item.checkState(0)==Qt.Checked for item,_ in self.rows)
            if not chosen: return
            answer=QMessageBox.question(self,'确认本次额外清理',f'处理明确选中的 {chosen} 项？\n文件移入隔离区；注册表仅导出备份并保留原项。未选中项保留。',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if answer!=QMessageBox.Yes: return
            reviewed=self._reviewed()
            self._run(lambda:self.workflow.cleanup(reviewed),self._cleanup_done,'正在备份和隔离选中项…')
        else:
            self.accept()

    def _official_done(self,rep):
        self.report=rep
        if not rep.official_ok:
            self._show_result(rep,'官方卸载未完成','未执行任何额外清理。可关闭后检查厂商卸载窗口或重启要求。\n'+rep.official_detail)
            return
        mode = self.mode.currentData()
        self._run(lambda:self.workflow.scan(mode),self._scan_done,'官方卸载已完成，正在重新扫描残留…')

    def _scan_done(self,entry):
        self.candidates=entry; self.tree.blockSignals(True); self.tree.clear(); self.rows=[]
        groups={}
        for item in entry.leftovers:
            group='注册表（只导出，不删除）' if item.kind=='key' else ('快捷方式' if item.kind=='file' else '文件 / 数据目录（隔离）')
            if group not in groups:
                top=QTreeWidgetItem([group]); self.tree.addTopLevelItem(top); groups[group]=top
            row=QTreeWidgetItem([item.path,scanner.human_size(item.size),item.basis,item.confidence])
            row.setToolTip(0,item.path); row.setToolTip(2,item.basis)
            if item.selectable:
                row.setFlags(row.flags()|Qt.ItemIsUserCheckable); row.setCheckState(0,Qt.Unchecked)
            else:
                row.setFlags(row.flags() & ~Qt.ItemIsEnabled)
                row.setText(3, '不可隔离')
            row.setData(0,Qt.UserRole,item.path); groups[group].addChild(row); self.rows.append((row,item))
        self.tree.expandAll(); self.tree.blockSignals(False)
        total=sum(i.size for i in entry.leftovers)
        self.review_summary.setText(f'官方卸载已完成 · {leftovers.PROFILES[self.mode.currentData()][0]}扫描发现 {len(entry.leftovers)} 项候选，约 {scanner.human_size(total)}。请核对完整位置后选择。')
        self.status.setText('等待你审阅；当前没有选中任何项目')
        self._set_phase(1)

    def _selection_changed(self,*args):
        chosen=[item for row,item in self.rows if row.checkState(0)==Qt.Checked]
        self.selected_label.setText(f'已选择 {len(chosen)} 项 · {scanner.human_size(sum(i.size for i in chosen))}')
        if self.pages.currentIndex()==1:
            self.btn_primary.setEnabled(bool(chosen) and not self._busy)

    def _check_all(self,checked):
        if self._busy: return
        for row,item in self.rows:
            if item.selectable:
                row.setCheckState(0,Qt.Checked if checked else Qt.Unchecked)

    def _copy_path(self):
        row=self.tree.currentItem()
        if row and row.data(0,Qt.UserRole): QApplication.clipboard().setText(row.data(0,Qt.UserRole))

    def _reviewed(self):
        reviewed=copy.deepcopy(self.candidates)
        selected={leftovers.identity(item) for row,item in self.rows if row.checkState(0)==Qt.Checked}
        for item in reviewed.leftovers: item.checked=leftovers.identity(item) in selected
        return reviewed

    def _secondary(self):
        if self._busy: return
        if self.pages.currentIndex()==1:
            self._run(self.workflow.finish_without_cleanup,self._cleanup_done,'保存保留全部的处理结果…')
        elif self.pages.currentIndex()==2:
            from .recovery_dialog import RecoveryDialog
            RecoveryDialog(self).exec_()
        else:
            self.reject()

    def _cleanup_done(self,rep):
        self.report=rep
        title='已完成本次处理' if not rep.failed else '部分项目已保留'
        text=(f'{len(rep.removed)} 项已处理，{len(rep.retained)} 项按选择保留，{len(rep.failed)} 项未能处理。\n'
              f'隔离数据约 {scanner.human_size(rep.quarantined_bytes)}，仍占磁盘空间。\n'
              '可恢复范围仅限本工具的隔离文件和注册表导出；无法撤销厂商卸载器本身。')
        if rep.recovery_session: text+='\n恢复记录：'+rep.recovery_session[:12]
        self._show_result(rep,title,text)

    def _show_result(self,rep,title,text):
        self.result_title.setText(title); self.result_text.setText(text)
        self._set_phase(2); self.status.setText('处理结果已保存；可导出报告')
        self.btn_primary.setEnabled(True); self.btn_secondary.setEnabled(True)
        self.result_ready.emit(rep)

    def _log(self,text):
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _export_report(self):
        if not self.report: return
        target,_=QFileDialog.getSaveFileName(self,'导出处理报告','卸载报告.json','JSON (*.json)')
        if not target: return
        try:
            from dataclasses import asdict
            Path(target).write_text(json.dumps(asdict(self.report),ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self,'导出失败',str(exc))

    def reject(self):
        if self._busy or any(w.isRunning() for w in self._workers):
            self.status.setText('当前任务仍在运行，请等待完成；不会强制中断卸载器。'); return
        super().reject()

    def closeEvent(self,event):
        if self._busy or any(w.isRunning() for w in self._workers):
            self.status.setText('当前任务仍在运行，请等待完成。'); event.ignore(); return
        event.accept()

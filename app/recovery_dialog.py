"""Recovery center: explicit selection, no overwrite, no permanent-delete action.

Visual language: Apple system-settings style, driven entirely by ``theme``.
Behaviour, signals and public attributes are unchanged.
"""
from __future__ import annotations
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPlainTextEdit, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout)
from .scanner import human_size
from .wizard import ShellDialog, Work


class RecoveryDialog(ShellDialog):
    def __init__(self,parent=None,store=None):
        super().__init__(parent)
        from .recovery import RecoveryStore
        self.store=store
        self._workers=set(); self._busy=False
        self._build()
        self._restyle()
        try:
            self.store=store or RecoveryStore()
            self.load()
        except Exception as exc:
            self.log.appendPlainText(str(exc)); self.status.setText('恢复区不可用'); self.restore_btn.setEnabled(False)

    def _build(self):
        layout = self._init_shell('恢复中心', (800, 540), (1000, 680))

        title = QLabel('恢复中心')
        title.setProperty('role', 'h1')
        layout.addWidget(title)

        hint = QLabel('恢复本工具隔离的文件和导出的注册表。不会覆盖原位置已存在的文件；无法撤销厂商卸载器的操作。')
        hint.setWordWrap(True)
        hint.setProperty('role', 'meta')
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['应用 / 原位置', '类型 / 状态', '大小'])
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 132)
        self.tree.setColumnWidth(2, 92)
        layout.addWidget(self.tree, 1)

        self.log = QPlainTextEdit()
        self.log.setObjectName('Log')
        self.log.setReadOnly(True)
        self.log.setFixedHeight(96)
        layout.addWidget(self.log)

        bottom = QHBoxLayout()
        bottom.setSpacing(9)
        self.status = QLabel('正在读取恢复记录…')
        self.status.setProperty('role', 'faint')
        bottom.addWidget(self.status, 1)

        self.refresh = QPushButton('刷新')
        self.refresh.setObjectName('Secondary')
        self.refresh.clicked.connect(self.load)
        bottom.addWidget(self.refresh)

        self.restore_btn = QPushButton('还原选中项')
        self.restore_btn.setObjectName('Primary')
        self.restore_btn.clicked.connect(self.restore_selected)
        bottom.addWidget(self.restore_btn)

        self.close_btn = QPushButton('关闭')
        self.close_btn.setObjectName('Secondary')
        self.close_btn.clicked.connect(self.reject)
        bottom.addWidget(self.close_btn)
        layout.addLayout(bottom)

        self.tree.itemChanged.connect(self._selected_changed)

    def _selected_changed(self,*args):
        count=len(self._selected())
        self.restore_btn.setEnabled(bool(count) and not self._busy)
        if not self._busy: self.status.setText(f'已选择 {count} 项')

    def _selected(self):
        out=[]
        for n in range(self.tree.topLevelItemCount()):
            group=self.tree.topLevelItem(n)
            for j in range(group.childCount()):
                row=group.child(j)
                if row.checkState(0)==Qt.Checked and row.data(0,Qt.UserRole): out.append(row.data(0,Qt.UserRole))
        return out

    def load(self):
        if self._busy or not self.store: return
        self.tree.blockSignals(True); self.tree.clear(); count=0
        try:
            for session in self.store.list_sessions():
                session_id=session['session_id']
                if session.get('status') == 'invalid':
                    self.log.appendPlainText('记录校验失败：'+session_id+' · '+session.get('error',''))
                    continue
                group=QTreeWidgetItem([session.get('app_name','应用')+' · '+session.get('created_at',session.get('timestamp',session_id[:12]))])
                self.tree.addTopLevelItem(group)
                for item in self.store.items(session_id):
                    status=item.get('status','未知')
                    labels={'quarantined':'已隔离','quarantined_changed':'内容变化，待核对','verification_pending':'校验未完成，需确认','backed_up':'注册表导出','restored':'已还原','prepared':'待核验','restoring':'恢复中断','failed':'未处理'}
                    row=QTreeWidgetItem([item.get('original_path',''),labels.get(status,status),human_size(item.get('bytes',0))])
                    row.setToolTip(0,item.get('original_path',''))
                    row.setTextAlignment(2,Qt.AlignRight|Qt.AlignVCenter)
                    group.addChild(row)
                    if status in ('quarantined','quarantined_changed','backed_up','prepared','restoring','verification_pending'):
                        row.setFlags(row.flags()|Qt.ItemIsUserCheckable); row.setCheckState(0,Qt.Unchecked)
                        row.setData(0,Qt.UserRole,(session_id,item['item_id'],status in ('prepared','verification_pending'))); count+=1
                group.setExpanded(True)
            self.status.setText(f'{count} 项可审阅恢复')
        except Exception as exc:
            self.log.appendPlainText('读取失败：'+str(exc)); self.status.setText('部分记录无法读取，已拒绝使用')
        finally:
            self.tree.blockSignals(False)
        self.restore_btn.setEnabled(False)

    def restore_selected(self):
        chosen=self._selected()
        if self._busy or not chosen: return
        pending = any(item[2] for item in chosen)
        if pending:
            message = ('选中项包含中断后校验未完成的记录。内容可能与操作前不同。\n'
                       '程序会重新核验隔离区当前内容，并在记录写入成功后尝试恢复。原位置存在时不覆盖。\n'
                       '请先核对项目及其隔离区内容，确定继续？')
        else:
            message = f'还原选中的 {len(chosen)} 项？\n文件原位置存在时会保留双方并报告冲突。注册表导入会写回此前导出的值，可能改变现有设置。'
        answer=QMessageBox.question(self,'确认还原',message,QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
        if answer!=QMessageBox.Yes: return
        self._busy=True; self.tree.setEnabled(False); self.restore_btn.setEnabled(False); self.refresh.setEnabled(False); self.close_btn.setEnabled(False)
        self.status.setText('正在校验并还原…')
        def task():
            results=[]
            for session_id,item_id,needs_consent in chosen:
                try: results.append(self.store.restore(session_id,item_id,allow_changed=needs_consent))
                except Exception as exc: results.append({'status':'failed','error':str(exc)})
            return results
        worker=Work(task,self); self._workers.add(worker)
        worker.done.connect(self._done); worker.error.connect(lambda text:self._done([{'status':'failed','error':text}]))
        worker.finished.connect(lambda:self._finished(worker)); worker.start()

    def _finished(self,worker):
        self._workers.discard(worker); worker.deleteLater()

    def _done(self,results):
        self._busy=False; self.tree.setEnabled(True); self.refresh.setEnabled(True); self.close_btn.setEnabled(True)
        for result in results:
            self.log.appendPlainText(f"{result.get('status')} · {result.get('original_path','')} {result.get('error','')}")
        self.load()
        good=sum(r.get('status')=='restored' for r in results)
        self.status.setText(f'已还原 {good} 项；其他 {len(results)-good} 项保留，请查看日志')

    def reject(self):
        if self._busy or any(w.isRunning() for w in self._workers): return
        super().reject()

    def closeEvent(self,event):
        if self._busy or any(w.isRunning() for w in self._workers): event.ignore(); return
        event.accept()

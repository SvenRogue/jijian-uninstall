"""Two-stage uninstall workflow: vendor first, then a separately reviewed plan.

Unselected or newly discovered positions never become cleanup consent. File
cleanup is quarantine only; registry deletion requires a verified export first.
"""
from __future__ import annotations
import copy
import os
from datetime import datetime
from . import engine, leftovers, reg, scanner
from .scanner import AppEntry


class WorkflowError(ValueError):
    pass


class UninstallWorkflow:
    def __init__(self, entry: AppEntry, log, progress=None, store=None):
        self.entry = copy.deepcopy(entry)
        if not self.entry.install_location:
            self.entry.install_location = scanner._derive_install_location(self.entry)
        self.log = log
        self.progress = progress or (lambda n: None)
        self.engine = engine.Uninstaller(log, self.progress)
        self.store = store
        self.phase = 'prepare'
        self.report = None
        self.candidates = None
        self._approved_candidates = {}
        self._approved_identities = {}
        self.mode = 'standard'

    def uninstall(self, dry_run=False):
        if self.phase != 'prepare':
            raise WorkflowError('官方卸载阶段不能重复执行')
        self.phase = 'uninstall'
        # The first stage never performs extra cleanup.
        official_entry = copy.deepcopy(self.entry)
        official_entry.leftovers = []
        self.report = self.engine.run(official_entry, do_registry=False,
                                      do_appdata=False, do_shortcuts=False,
                                      dry_run=dry_run)
        self.phase = 'preview' if dry_run else ('scan' if self.report.official_ok else 'failed')
        self.report.phase = self.phase
        return self.report

    def scan(self, mode='standard'):
        if self.phase not in ('scan', 'review') or not self.report or not self.report.official_ok:
            raise WorkflowError('仅在确认官方卸载成功后扫描残留')
        self.mode = mode
        self.log(f'扫描模式：{leftovers.PROFILES[mode][0]}；扫描只生成候选，不执行删除')
        result = leftovers.scan_leftovers(self.entry, mode)
        self._approved_identities = {}
        file_items = [i for i in result.leftovers if i.kind != 'key']
        if file_items:
            try:
                if self.store is None:
                    from .recovery import RecoveryStore
                    self.store = RecoveryStore()
            except Exception as exc:
                self.log(f'恢复区不可用，文件候选仅供查看：{exc}')
                for item in file_items:
                    item.selectable = False
                    item.basis = '无法初始化恢复区，无法隔离；原文件保留'
        for index, item in enumerate(file_items):
            if item.selectable:
                try:
                    proof = self.store.probe_identity(item.path)
                    self._approved_identities[leftovers.identity(item)] = copy.deepcopy(proof)
                except Exception as exc:
                    item.selectable = False
                    item.basis = '无法验证项目身份或内容，已保留：' + str(exc)
            self.progress(int((index + 1) * 100 / max(1, len(file_items))))
        self.candidates = copy.deepcopy(result)
        self._approved_candidates = {leftovers.identity(i): copy.deepcopy(i) for i in result.leftovers}
        self.phase = self.report.phase = 'review'
        self.progress(100)
        return copy.deepcopy(result)

    def cleanup(self, reviewed: AppEntry):
        if self.phase != 'review' or not self.report or not self.report.official_ok:
            raise WorkflowError('当前没有已审阅的残留清理阶段')
        if reviewed.uid != self.entry.uid:
            raise WorkflowError('清理对象与本次卸载对象不一致')
        selected = [i for i in reviewed.leftovers if i.checked]
        # Validate the complete plan before any write, not halfway through it.
        for item in selected:
            approved = self._approved_candidates.get(leftovers.identity(item))
            if not approved or not approved.selectable:
                raise WorkflowError('清理计划含有未扫描或无法验证的位置')
            if item.kind != 'key' and leftovers.identity(item) not in self._approved_identities:
                raise WorkflowError('文件身份缺少可验证的扫描记录')
            safe = engine._safe_key(item.path) if item.kind == 'key' else engine._safe_path(item.path)
            if not safe:
                raise WorkflowError(f'拒绝不安全或已改变的位置：{item.path}')
        if len({leftovers.identity(i) for i in selected}) != len(selected):
            raise WorkflowError('清理计划包含重复项目')
        self.phase = self.report.phase = 'cleanup'
        rep = self.report
        rep.failed = []
        rep.remaining = []
        rep.retained = []
        rep.removed = []
        rep.removed_bytes = 0
        rep.quarantined_bytes = 0
        rep.recovery_session = ''
        session_id = ''
        if selected:
            try:
                if self.store is None:
                    from .recovery import RecoveryStore
                    self.store = RecoveryStore()
                session_id = self.store.create_session(self.entry.name)
                rep.recovery_session = session_id
            except Exception as exc:
                rep.failed.append(('recovery', str(exc)))
                rep.remaining = [i.path for i in selected if self.engine._exists(i)]
                self.log(f'恢复区不可用，所有残留保持原位：{exc}')
                self.phase = rep.phase = 'failed'
                return self.engine._finish(rep)
        for index, item in enumerate(selected):
            try:
                if not self.engine._exists(item):
                    self.log(f'已消失，跳过：{item.path}')
                    continue
                if item.kind == 'key':
                    backup = self.store.backup_registry(session_id, item.path)
                    if backup.get('status') != 'backed_up':
                        raise OSError(backup.get('error', '注册表备份失败'))
                    rep.retained.append(item.path)
                    self.log(f'已导出注册表备份，原项保留未删除：{item.path}')
                    continue
                else:
                    proof = self._approved_identities[leftovers.identity(item)]
                    moved = self.store.quarantine_path(session_id, item.path, expected_identity=proof)
                    if moved.get('status') == 'quarantined_changed':
                        rep.recovery_session = session_id
                        raise OSError('隔离期间内容发生变化；已保留在恢复中心，请核对并恢复')
                    if moved.get('status') != 'quarantined':
                        raise OSError(moved.get('error', '隔离失败，未作永久删除'))
                    rep.quarantined_bytes += max(0, int(moved.get('bytes', item.size)))
                    self.log(f'已移入可恢复隔离区：{item.path}')
                rep.removed.append(item.path)
            except Exception as exc:
                rep.failed.append((item.path, str(exc)))
                self.log(f'保留：{item.path} · {exc}')
            self.progress(int((index + 1) * 100 / max(1, len(selected))))
        selected_ids = {leftovers.identity(i) for i in selected}
        for item in self.candidates.leftovers:
            if self.engine._exists(item):
                if item.kind == 'key':
                    if item.path not in rep.retained:
                        rep.retained.append(item.path)
                elif leftovers.identity(item) in selected_ids:
                    rep.remaining.append(item.path)
                else:
                    rep.retained.append(item.path)
        self.phase = rep.phase = 'complete' if not rep.failed and not rep.remaining else 'partial'
        self.log(f'完成：{len(rep.removed)} 项已处理，{len(rep.retained)} 项按选择保留。隔离数据仍占用磁盘，可从恢复中心还原。')
        return self.engine._finish(rep)

    def finish_without_cleanup(self):
        if self.phase != 'review':
            raise WorkflowError('当前不在审阅阶段')
        reviewed = copy.deepcopy(self.candidates)
        for item in reviewed.leftovers:
            item.checked = False
        return self.cleanup(reviewed)

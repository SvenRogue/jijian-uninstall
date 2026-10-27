import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from app import leftovers, workflow
from app.engine import Report
from app.scanner import AppEntry, LeftoverItem


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app=AppEntry('Fixture',uid='fixture')
        self.app.leftovers=[LeftoverItem('dir',r'C:\Fixture\pre',checked=True)]
        self.store=Mock()
        self.store.create_session.return_value='fixture-session'
        self.store.probe_identity.return_value={'file_id':'original','sha256':'digest'}
        self.store.quarantine_path.return_value={'status':'quarantined','bytes':42}
        self.store.backup_registry.return_value={'status':'backed_up'}
        self.w=workflow.UninstallWorkflow(self.app,lambda _:None,store=self.store)
        self.a=LeftoverItem('dir',r'C:\Fixture\A',checked=False)
        self.b=LeftoverItem('dir',r'C:\Fixture\B',checked=False)
        self.c=LeftoverItem('key',r'HKCU\Software\Fixture',checked=False)

    def start_review(self):
        rep=Report(official_ok=True)
        with patch.object(self.w.engine,'run',return_value=rep) as run:
            self.w.uninstall()
        self.assertEqual(run.call_args.args[0].leftovers,[])
        result=copy.deepcopy(self.app); result.leftovers=[self.a,self.b,self.c]
        with patch('app.workflow.leftovers.scan_leftovers',return_value=result):
            return self.w.scan('standard')

    def test_failed_official_blocks_scan_and_cleanup(self):
        with patch.object(self.w.engine,'run',return_value=Report(official_ok=False)):
            self.w.uninstall()
        self.assertEqual(self.w.phase,'failed')
        with self.assertRaises(workflow.WorkflowError): self.w.scan()
        with self.assertRaises(workflow.WorkflowError): self.w.cleanup(self.app)
        self.store.create_session.assert_not_called()

    def test_review_only_selected_and_registry_is_backup_only(self):
        reviewed=self.start_review(); reviewed.leftovers[0].checked=True; reviewed.leftovers[2].checked=True
        calls=[]
        self.store.backup_registry.side_effect=lambda *a:(calls.append('backup') or {'status':'backed_up'})
        with patch('app.workflow.engine._safe_path',return_value=True), patch('app.workflow.engine._safe_key',return_value=True), patch.object(self.w.engine,'_exists',return_value=True), patch('app.workflow.reg.delete_tree_deep',side_effect=lambda p:(calls.append('delete') or True)), patch.object(self.w.engine,'_finish',side_effect=lambda r:r):
            result=self.w.cleanup(reviewed)
        self.assertEqual(calls,['backup'])
        self.store.quarantine_path.assert_called_once_with('fixture-session',self.a.path,expected_identity={'file_id':'original','sha256':'digest'})
        self.assertEqual(result.quarantined_bytes,42)
        self.assertIn(self.b.path,result.retained)
        self.assertNotIn(self.b.path,result.removed)

    def test_failed_backup_never_deletes_registry(self):
        reviewed=self.start_review(); reviewed.leftovers[2].checked=True
        self.store.backup_registry.return_value={'status':'failed','error':'access denied'}
        with patch('app.workflow.engine._safe_key',return_value=True),patch.object(self.w.engine,'_exists',return_value=True),patch('app.workflow.reg.delete_tree_deep') as deletion,patch.object(self.w.engine,'_finish',side_effect=lambda r:r):
            rep=self.w.cleanup(reviewed)
        deletion.assert_not_called(); self.assertTrue(rep.failed)

    def test_injected_candidate_or_duplicate_refused_before_changes(self):
        reviewed=self.start_review(); reviewed.leftovers.append(LeftoverItem('dir',r'C:\Other',checked=True))
        with self.assertRaises(workflow.WorkflowError): self.w.cleanup(reviewed)
        self.store.create_session.assert_not_called()
        reviewed=self.start_review() if False else copy.deepcopy(self.w.candidates)
        reviewed.leftovers[0].checked=True; reviewed.leftovers.append(copy.deepcopy(reviewed.leftovers[0]))
        with patch('app.workflow.engine._safe_path',return_value=True):
            with self.assertRaises(workflow.WorkflowError): self.w.cleanup(reviewed)
        self.store.create_session.assert_not_called()

    def test_keep_all_creates_no_vault(self):
        self.start_review()
        with patch.object(self.w.engine,'_exists',return_value=True),patch.object(self.w.engine,'_finish',side_effect=lambda r:r):
            rep=self.w.finish_without_cleanup()
        self.store.create_session.assert_not_called(); self.assertEqual(len(rep.retained),3)

    def test_unverified_identity_cannot_be_selected(self):
        self.store.probe_identity.side_effect=OSError('cannot lock')
        reviewed=self.start_review()
        self.assertFalse(reviewed.leftovers[0].selectable)
        reviewed.leftovers[0].checked=True
        with self.assertRaises(workflow.WorkflowError): self.w.cleanup(reviewed)
        self.store.create_session.assert_not_called()

    def test_dryrun_is_terminal_preview(self):
        with patch.object(self.w.engine,'run',return_value=Report(dry_run=True)):
            self.w.uninstall(dry_run=True)
        self.assertEqual(self.w.phase,'preview')
        with self.assertRaises(workflow.WorkflowError): self.w.scan()

    def test_real_fixture_quarantine_and_restore(self):
        from app.recovery import RecoveryStore
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp).resolve()
            source=base/'FixtureData'; source.mkdir(); (source/'note.txt').write_text('preserve',encoding='utf-8')
            store=RecoveryStore(base/'Vault')
            app=AppEntry('Fixture',uid='fixture')
            candidate=copy.deepcopy(app); candidate.leftovers=[LeftoverItem('dir',str(source),size=8,checked=False)]
            subject=workflow.UninstallWorkflow(app,lambda _:None,store=store)
            with patch.object(subject.engine,'run',return_value=Report(official_ok=True)), patch('app.workflow.leftovers.scan_leftovers',return_value=candidate), patch.object(subject.engine,'_finish',side_effect=lambda r:r):
                subject.uninstall(); reviewed=subject.scan(); reviewed.leftovers[0].checked=True
                report=subject.cleanup(reviewed)
            self.assertFalse(report.failed,report.failed)
            self.assertFalse(source.exists()); self.assertEqual(report.quarantined_bytes,8)
            item=store.items(report.recovery_session)[0]
            self.assertEqual(item['status'],'quarantined')
            restored=store.restore(report.recovery_session,item['item_id'])
            self.assertEqual(restored['status'],'restored',restored)
            self.assertEqual((source/'note.txt').read_text(encoding='utf-8'),'preserve')

    def test_scan_resets_all_selection_and_safe_limits_scope(self):
        e=copy.deepcopy(self.app)
        e.leftovers=[LeftoverItem('dir',r'C:\Fixture\A',note='安装目录',checked=True),LeftoverItem('dir',r'C:\Fixture\B',note='用户数据 / 缓存',checked=True)]
        with patch('app.leftovers.scanner.inventory',return_value=e):
            scan=leftovers.scan_leftovers(self.app,'safe')
        self.assertEqual(len(scan.leftovers),1); self.assertFalse(scan.leftovers[0].checked)
        self.assertEqual(scan.leftovers[0].confidence,'明确位置')


if __name__=='__main__': unittest.main()

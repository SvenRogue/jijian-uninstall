"""Isolated release regression tests. No installed app is scanned or uninstalled."""
import copy
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import engine
from app.scanner import AppEntry, LeftoverItem

class ReleaseEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logdir = patch.object(engine, 'LOG_DIR', Path(self.tmp.name) / 'reports')
        self.logdir.start()
        self.addCleanup(self.logdir.stop)
        self.u = engine.Uninstaller(lambda msg: None)
        self.app = AppEntry(name='ReleaseFixture', uninstall_type='nsis',
                            uninstall_string=r'"C:\Fixture App\uninstall.exe"')

    def test_preserves_reviewed_selection_and_never_reinventories(self):
        self.app.leftovers = [LeftoverItem('dir',r'C:\Fixture\chosen',checked=True),
                              LeftoverItem('dir',r'C:\Fixture\keep',checked=False)]
        with patch.object(engine.scanner,'inventory',side_effect=AssertionError('reinventoried')), \
             patch.object(self.u,'_run_official',return_value=(True,'ok')), \
             patch.object(self.u,'_exists',return_value=False), \
             patch.object(self.u,'_remove_dirs') as remove:
            self.u.run(self.app)
        self.assertEqual([i.path for i in remove.call_args.args[0].leftovers],
                         [r'C:\Fixture\chosen'])
        self.assertFalse(self.app.leftovers[1].checked)

    def test_failure_never_cleans_or_retries(self):
        with patch.object(self.u,'_run_official',return_value=(False,'cancelled')), \
             patch.object(self.u,'_remove_dirs') as dirs, \
             patch.object(self.u,'_remove_registry') as keys, \
             patch.object(self.u,'_remove_shortcuts') as links:
            rep = self.u.run(self.app)
        for fn in (dirs,keys,links): fn.assert_not_called()
        self.assertFalse(rep.clean)
        self.assertFalse(rep.official_ok)

    def test_dry_run_never_mutates_and_never_claims_success(self):
        with patch.object(self.u,'_run_official') as official, \
             patch.object(self.u,'_remove_dirs') as remove:
            rep = self.u.run(self.app,dry_run=True)
        official.assert_not_called(); remove.assert_not_called()
        self.assertTrue(rep.dry_run)
        self.assertFalse(rep.official_ok)
        self.assertFalse(rep.clean)
        self.assertEqual(rep.removed,[])

    def test_failure_report_cannot_be_clean(self):
        self.assertFalse(engine.Report().clean)
        self.assertFalse(engine.Report(official_ok=True,retained=['kept']).clean)
        self.assertTrue(engine.Report(official_ok=True).clean)

    def test_reused_instance_resets_all_state(self):
        self.u._removed_bytes=100
        self.u._deferred.append(('old','permission'))
        rep = self.u.run(self.app,dry_run=True)
        self.assertEqual(rep.removed_bytes,0)
        self.assertEqual(self.u._deferred,[])
        other = engine.Uninstaller(lambda _:None)
        self.assertIsNot(other._deferred,self.u._deferred)

    def test_quoted_and_unquoted_vendor_commands(self):
        for raw in (r'"C:\Fixture App\uninstall.exe" /vendor="keep me"',
                    r'C:\Fixture App\uninstall.exe /vendor="keep me"'):
            self.app.uninstall_string=raw
            cmd=self.u._official_command_native(self.app)
            self.assertEqual(cmd[0],r'C:\Fixture App\uninstall.exe')
            self.assertEqual(cmd[-1],'/S')
            self.assertIn('/vendor=keep me',cmd)

    def test_msi_is_separate_argv_and_install_switch_becomes_uninstall(self):
        self.app.uninstall_type='msiexec'
        self.app.uninstall_string='MsiExec.exe /I{12345678-1234-1234-1234-123456789ABC}'
        cmd=self.u._official_command_native(self.app)
        self.assertEqual(cmd[0],'MsiExec.exe')
        self.assertTrue(cmd[1].startswith('/X{'))
        self.assertIn('/qn',cmd)

    def test_appx_uses_fullname_property_and_terminating_errors(self):
        self.app.uninstall_type='appx'
        self.app._pkg_family='Fixture.App_abcd1234'
        cmd=self.u._official_command_native(self.app)
        ps=cmd[-1]
        self.assertIn('PackageFamilyName -eq',ps)
        self.assertIn('Remove-AppxPackage -Package $_.PackageFullName',ps)
        self.assertIn("$ErrorActionPreference='Stop'",ps)
        self.assertNotIn('-PackageFamilyName',ps)
        self.app._pkg_family="Fixture';throw 'injected"
        with self.assertRaises(ValueError): self.u._official_command_native(self.app)

    def test_cmd_hosts_rejected(self):
        self.app.uninstall_string='cmd.exe /c del C:\\data'
        with self.assertRaises(ValueError): self.u._official_command(self.app)

    def test_nonzero_cancel_and_reboot_prevent_cleanup(self):
        for rc in (1,1602,1641,3010):
            with patch.object(engine.subprocess,'run',return_value=Mock(returncode=rc)) as run:
                ok,_=self.u._run_official(self.app)
            self.assertFalse(ok)
            self.assertEqual(run.call_count,1)
            self.assertFalse(run.call_args.kwargs['shell'])

    def test_zero_without_verified_disappearance_is_failure(self):
        self.app._arp_key=r'HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Fixture'
        with patch.object(engine.subprocess,'run',return_value=Mock(returncode=0)), \
             patch.object(engine.reg,'exists',return_value=True):
            self.assertFalse(self.u._run_official(self.app)[0])
        with patch.object(engine.subprocess,'run',return_value=Mock(returncode=0)), \
             patch.object(engine.reg,'exists',return_value=False):
            self.assertTrue(self.u._run_official(self.app)[0])

    def test_broad_and_injection_paths_rejected_without_shell(self):
        paths=['C:\\',r'C:\Program Files',r'C:\Program Files\Tencent',
               r'C:\Windows\Temp',r'C:\Program Files\WindowsApps\App',
               r'C:\Fixture & other',r'C:\Fixture\..\Windows',
               r'\\server\share\App']
        with patch.object(engine.shutil,'rmtree') as rm, patch.object(engine.subprocess,'run') as run:
            for p in paths:
                self.assertFalse(self.u._delete([p]),p)
        rm.assert_not_called(); run.assert_not_called()

    def test_shared_registry_keys_rejected(self):
        for p in (r'HKCU\Software',r'HKCU\Software\Tencent',r'HKLM\Software\Microsoft',
                  r'HKCU\Software\Classes\App',r'HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall'):
            self.assertFalse(engine._safe_key(p),p)

    def test_categories_disabled_do_not_clean(self):
        self.app.leftovers=[LeftoverItem('dir',r'C:\Fixture\App',checked=True),
                            LeftoverItem('key',r'HKCU\Software\Fixture',checked=True),
                            LeftoverItem('file',r'C:\Fixture\App.lnk',checked=True)]
        with patch.object(self.u,'_run_official',return_value=(True,'ok')), \
             patch.object(self.u,'_exists',return_value=True), \
             patch.object(self.u,'_delete') as delete, \
             patch.object(engine.reg,'delete_tree_deep') as registry:
            rep=self.u.run(self.app,do_registry=False,do_appdata=False,do_shortcuts=False)
        delete.assert_not_called(); registry.assert_not_called()
        self.assertEqual(len(rep.retained),3)
        self.assertFalse(rep.clean)

    def test_delete_uses_python_api_and_refuses_reparse(self):
        with patch.object(engine,'_safe_path',return_value=True), \
             patch.object(engine.os.path,'isdir',return_value=True), \
             patch.object(engine.os.path,'lexists',return_value=False), \
             patch.object(engine.shutil,'rmtree') as remove, \
             patch.object(engine.subprocess,'run') as shell:
            self.assertTrue(self.u._delete([r'C:\Fixture\App']))
        remove.assert_called_once_with(r'C:\Fixture\App')
        shell.assert_not_called()
        with patch.object(engine.Path,'lstat',return_value=Mock(st_file_attributes=0x400,st_mode=0)):
            self.assertFalse(engine._safe_path(r'C:\Fixture\App'))

    def test_permission_failure_reported_without_system_fallback(self):
        self.app.leftovers=[LeftoverItem('dir',r'C:\Fixture\App',checked=True)]
        with patch.object(self.u,'_exists',return_value=True), \
             patch.object(engine,'_safe_path',return_value=True), \
             patch.object(self.u,'_delete',return_value=False), \
             patch.object(engine.subprocess,'run') as run:
            self.u._remove_dirs(self.app)
            self.u._sweep_protected()
        run.assert_not_called()
        self.assertTrue(self.u._report.failed)

class WorkerLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.qt=QApplication.instance() or QApplication([])

    def test_rapid_selection_retains_both_inventory_threads(self):
        from PyQt5.QtCore import QThread, pyqtSignal
        from app import ui
        with patch.object(ui.QTimer,'singleShot'):
            window=ui.MainWindow()
        release=threading.Event()
        class Inventory(QThread):
            done=pyqtSignal(object)
            def __init__(self,entry):
                super().__init__(); self.entry=copy.deepcopy(entry)
            def run(self):
                release.wait(3); self.done.emit(self.entry)
        a=AppEntry(name='FirstFixture'); b=AppEntry(name='SecondFixture')
        with patch.object(ui,'InventoryWorker',Inventory), \
             patch.object(window,'_render_detail'), \
             patch.object(window,'_on_inventory') as result:
            window._on_select(Mock(data=Mock(return_value=a)),None)
            first=window._inv_worker
            window._on_select(Mock(data=Mock(return_value=b)),None)
            second=window._inv_worker
            self.assertIn(first,window._workers)
            self.assertIn(second,window._workers)
            release.set(); first.wait(2000); second.wait(2000)
            for _ in range(10): self.qt.processEvents()
        self.assertFalse(window._workers)
        window.close()

    def test_worker_reference_retained_and_close_waits(self):
        from PyQt5.QtCore import QThread, QTimer
        from PyQt5.QtGui import QCloseEvent
        from app import ui
        with patch.object(ui.QTimer,'singleShot'):
            window=ui.MainWindow()
        ready=threading.Event(); release=threading.Event()
        class Worker(QThread):
            def run(self):
                ready.set(); release.wait(3)
        worker=Worker()
        window._track_worker(worker)
        worker.start(); self.assertTrue(ready.wait(1))
        event=QCloseEvent()
        window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertIn(worker,window._workers)
        release.set(); worker.wait(2000)
        for _ in range(10): self.qt.processEvents()
        self.assertFalse(window._workers)
        window.close()

if __name__=='__main__':
    unittest.main()

import copy
import unittest
from unittest.mock import Mock, patch
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from app.scanner import AppEntry, LeftoverItem
from app.wizard import UninstallWizard
from app.recovery_dialog import RecoveryDialog


class WizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt=QApplication.instance() or QApplication([])

    def test_review_is_unchecked_and_preserves_explicit_selection(self):
        entry=AppEntry('Fixture',uid='id')
        entry.leftovers=[LeftoverItem('dir',r'C:\Fixture\one',size=20,checked=True,basis='exact',confidence='需核对'),LeftoverItem('key',r'HKCU\Software\Fixture',checked=True)]
        dlg=UninstallWizard(entry,workflow=Mock())
        dlg._scan_done(entry)
        self.assertEqual(len(dlg.rows),2)
        self.assertFalse(dlg.btn_primary.isEnabled())
        self.assertTrue(all(row.checkState(0)==Qt.Unchecked for row,_ in dlg.rows))
        dlg.rows[1][0].setCheckState(0,Qt.Checked)
        result=dlg._reviewed()
        self.assertFalse(result.leftovers[0].checked); self.assertTrue(result.leftovers[1].checked)
        self.assertTrue(dlg.btn_primary.isEnabled())
        dlg.close()

    def test_recovery_dialog_shows_existing_entries_unselected(self):
        store=Mock()
        store.list_sessions.return_value=[{'session_id':'s','app_name':'Fixture','timestamp':'2026'}]
        store.items.return_value=[{'item_id':'i','original_path':r'C:\Fixture','status':'quarantined','bytes':40}]
        dlg=RecoveryDialog(store=store)
        self.assertEqual(dlg.tree.topLevelItemCount(),1)
        row=dlg.tree.topLevelItem(0).child(0)
        self.assertEqual(row.checkState(0),Qt.Unchecked)
        self.assertFalse(dlg.restore_btn.isEnabled())
        row.setCheckState(0,Qt.Checked)
        self.assertTrue(dlg.restore_btn.isEnabled())
        self.assertEqual(dlg._selected(),[('s','i',False)])
        dlg.close()


if __name__=='__main__': unittest.main()

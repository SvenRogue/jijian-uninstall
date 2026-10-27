"""Isolated recovery tests: only temporary files, registry subprocess mocked."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from app import recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.vault = recovery.RecoveryStore(self.base/'vault')
        self.sid = self.vault.create_session('Fixture 应用')

    def source(self, name='source.txt', content=b'original bytes'):
        path = self.base/name
        path.write_bytes(content)
        return path

    def payload(self, item):
        return self.vault.root/self.sid/item['stored_path']

    def export(self, argv, **kwargs):
        self.assertEqual(argv[1], 'export')
        data = ('Windows Registry Editor Version 5.00\r\n\r\n['+argv[2]+']\r\n"Flag"="yes"\r\n').encode('utf-16')
        Path(argv[3]).write_bytes(data)
        return subprocess.CompletedProcess(argv,0)

    def test_file_roundtrip_and_detached_lists(self):
        original = self.source()
        item = self.vault.quarantine_path(self.sid,original)
        self.assertEqual(item['status'],'quarantined')
        self.assertFalse(original.exists())
        self.assertEqual(self.payload(item).read_bytes(),b'original bytes')
        data = self.vault.items(self.sid)
        data[0]['original_path']='evil'
        self.assertEqual(self.vault.items(self.sid)[0]['original_path'],str(original))
        self.assertEqual(self.vault.list_sessions()[0]['recoverable_count'],1)
        self.assertEqual(self.vault.restore(self.sid,item['item_id'])['status'],'restored')
        self.assertEqual(original.read_bytes(),b'original bytes')
        self.assertFalse(self.payload(item).exists())

    def test_directory_roundtrip(self):
        original=self.base/'app-data'
        (original/'nested').mkdir(parents=True)
        (original/'nested'/'data').write_bytes(b'123')
        (original/'empty').mkdir()
        item=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(item['bytes'],3)
        self.assertEqual(item['kind'],'dir')
        self.assertEqual(self.vault.restore(self.sid,item['item_id'])['status'],'restored')
        self.assertEqual((original/'nested'/'data').read_bytes(),b'123')
        self.assertTrue((original/'empty').is_dir())

    def test_no_overwrite_existing_destination(self):
        original=self.source()
        item=self.vault.quarantine_path(self.sid,original)
        original.write_bytes(b'new data')
        result=self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(result['status'],'conflict')
        self.assertEqual(original.read_bytes(),b'new data')
        self.assertTrue(self.payload(item).exists())
        self.assertEqual(self.vault.items(self.sid)[0]['status'],'quarantined')

    def test_journal_intent_exists_before_source_rename(self):
        original=self.source()
        real_move=recovery._WindowsPinned.move_to
        observed=[]
        def move(pinned,target):
            record=self.vault.items(self.sid)[0]
            observed.append(record['status'])
            self.assertEqual(record['status'],'prepared')
            self.assertTrue(original.exists())
            return real_move(pinned,target)
        with patch.object(recovery._WindowsPinned,'move_to',move):
            item=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(observed,['prepared'])
        self.assertEqual(item['status'],'quarantined')

    def test_prejournal_failure_keeps_source(self):
        original=self.source()
        with patch.object(self.vault,'_write',side_effect=OSError('disk full')):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(original.exists())
        self.assertEqual(self.vault.items(self.sid),[])

    def test_move_failure_keeps_source(self):
        original=self.source()
        with patch.object(recovery._WindowsPinned,'move_to',side_effect=PermissionError('denied')):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(original.exists())

    def test_cross_volume_rename_fails_without_copy_fallback(self):
        original=self.source()
        with patch.object(recovery._WindowsPinned,'move_to',side_effect=OSError(errno.EXDEV,'cross device')):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(original.exists())
        self.assertFalse(self.payload(result).exists())

    def test_postjournal_failure_rolls_back_instead_of_claiming_success(self):
        original=self.source()
        real_write=self.vault._write
        calls=0
        def write(sid,manifest):
            nonlocal calls
            calls+=1
            if calls>1:
                raise OSError('journal disk full after move')
            return real_write(sid,manifest)
        with patch.object(self.vault,'_write',side_effect=write):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertFalse(result.get('needs_review'))
        self.assertTrue(original.exists())
        self.assertEqual(original.read_bytes(),b'original bytes')
        self.assertFalse(self.payload(result).exists())

    def test_checksum_payload_corruption_is_not_restored(self):
        original=self.source()
        item=self.vault.quarantine_path(self.sid,original)
        self.payload(item).write_bytes(b'tampered')
        result=self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(result['status'],'failed')
        self.assertFalse(original.exists())

    def test_changed_payload_requires_explicit_consent_then_restores_measured_content(self):
        original=self.source()
        item=self.vault.quarantine_path(self.sid,original)
        self.payload(item).write_bytes(b'changed while interrupted')
        refused=self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(refused['status'],'failed')
        self.assertFalse(original.exists())
        self.assertIn('consent',refused['error'])
        consented=self.vault.restore(self.sid,item['item_id'],allow_changed=True)
        self.assertEqual(consented['status'],'restored',consented)
        self.assertEqual(original.read_bytes(),b'changed while interrupted')

    def test_manifest_authentication_and_traversal_fail_closed(self):
        original=self.source()
        item=self.vault.quarantine_path(self.sid,original)
        manifest=self.vault.root/self.sid/'manifest.json'
        value=json.loads(manifest.read_text(encoding='utf-8'))
        value['payload']['items'][0]['stored_path']='../../somewhere.exe'
        value['checksum']=hashlib.sha256(recovery._canonical(value['payload'])).hexdigest()
        manifest.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaises(recovery.RecoveryError):
            self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(self.vault.list_sessions()[0]['status'],'invalid')
        self.assertFalse(original.exists())

    def test_even_signed_traversal_record_is_refused(self):
        item=self.vault.quarantine_path(self.sid,self.source())
        manifest=self.vault._read(self.sid)
        manifest['items'][0]['stored_path']='../payload/elsewhere'
        self.vault._write(self.sid,manifest)
        with self.assertRaises(recovery.RecoveryError):
            self.vault.restore(self.sid,item['item_id'])

    def test_protected_original_revalidated_after_journal_load(self):
        item=self.vault.quarantine_path(self.sid,self.source())
        with patch.object(recovery.scanner,'path_is_safe',return_value=False):
            with self.assertRaises(recovery.RecoveryError):
                self.vault.restore(self.sid,item['item_id'])

    def test_vault_and_ancestor_cannot_be_quarantined(self):
        for path in (self.vault.root,self.base,self.vault.root/self.sid):
            self.assertEqual(self.vault.quarantine_path(self.sid,path)['status'],'failed')
            self.assertTrue(path.exists())

    def test_nested_reparse_point_rejected_before_mutation(self):
        original=self.base/'tree'
        original.mkdir()
        self.source('tree/leaf')
        real_lstat=Path.lstat
        def lstat(path,*args,**kwargs):
            info=real_lstat(path,*args,**kwargs)
            if path.name=='leaf':
                class Fake:
                    st_mode=stat.S_IFLNK
                    st_file_attributes=0x400
                return Fake()
            return info
        with patch.object(Path,'lstat',lstat):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertTrue((original/'leaf').exists())

    def test_bounded_tree_scan_preserves_source(self):
        original=self.base/'tree'
        original.mkdir()
        (original/'a').write_bytes(b'a')
        with patch.object(recovery,'MAX_ENTRIES',1):
            result=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(original.exists())

    def test_threaded_items_do_not_lose_journal_entries(self):
        sources=[self.source(f'item-{n}') for n in range(8)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            records=list(pool.map(lambda p:self.vault.quarantine_path(self.sid,p),sources))
        self.assertTrue(all(r['status']=='quarantined' for r in records))
        self.assertEqual(len(self.vault.items(self.sid)),8)

    def test_invalid_identifiers_fail_closed(self):
        for sid in ('../x','a'*31,'a'*33,'g'*32):
            with self.assertRaises(recovery.RecoveryError):
                self.vault.items(sid)

    def test_scan_identity_rejects_same_size_content_change(self):
        original=self.source(content=b'abc')
        approved=self.vault.probe_identity(original)
        original.write_bytes(b'xyz')
        item=self.vault.quarantine_path(self.sid,original,expected_identity=approved)
        self.assertEqual(item['status'],'failed')
        self.assertEqual(original.read_bytes(),b'xyz')
        self.assertEqual(self.vault.items(self.sid),[])

    def test_scan_identity_rejects_replaced_root_with_identical_bytes(self):
        original=self.source(content=b'abc')
        approved=self.vault.probe_identity(original)
        original.rename(self.base/'old-reviewed')
        original.write_bytes(b'abc')
        item=self.vault.quarantine_path(self.sid,original,expected_identity=approved)
        self.assertEqual(item['status'],'failed')
        self.assertTrue(original.exists())
        self.assertEqual((self.base/'old-reviewed').read_bytes(),b'abc')

    def test_last_instant_root_swap_blocked_by_native_handle(self):
        original=self.source()
        approved=self.vault.probe_identity(original)
        real_move=recovery._WindowsPinned.move_to
        blocked=[]
        displaced=self.base/'displaced'
        def attack(pinned,target):
            try:
                os.replace(original,displaced)
            except PermissionError:
                blocked.append(True)
            else:
                original.write_bytes(b'unreviewed replacement')
            return real_move(pinned,target)
        with patch.object(recovery._WindowsPinned,'move_to',attack):
            item=self.vault.quarantine_path(self.sid,original,expected_identity=approved)
        self.assertEqual(blocked,[True])
        self.assertEqual(item['status'],'quarantined')
        self.assertFalse(displaced.exists())
        self.assertEqual(self.payload(item).read_bytes(),b'original bytes')
        self.assertEqual(self.vault.restore(self.sid,item['item_id'])['status'],'restored')

    def test_handle_rename_never_overwrites_late_destination(self):
        original=self.source()
        real_move=recovery._WindowsPinned.move_to
        def collision(pinned,target):
            Path(target).write_bytes(b'late occupant')
            return real_move(pinned,target)
        with patch.object(recovery._WindowsPinned,'move_to',collision):
            item=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(item['status'],'failed')
        self.assertEqual(original.read_bytes(),b'original bytes')
        self.assertEqual(self.payload(item).read_bytes(),b'late occupant')

    def test_descendant_changed_during_move_is_recoverable_not_clean(self):
        original=self.base/'live-data'
        original.mkdir()
        (original/'reviewed').write_bytes(b'old')
        approved=self.vault.probe_identity(original)
        real_move=recovery._WindowsPinned.move_to
        def mutate(pinned,target):
            real_move(pinned,target)
            (Path(target)/'arrived-during-move').write_bytes(b'new')
        with patch.object(recovery._WindowsPinned,'move_to',mutate):
            item=self.vault.quarantine_path(self.sid,original,expected_identity=approved)
        self.assertEqual(item['status'],'quarantined_changed')
        self.assertTrue(item['needs_review'])
        self.assertEqual(self.vault.list_sessions()[0]['recoverable_count'],1)
        self.assertEqual(self.vault.restore(self.sid,item['item_id'])['status'],'restored')
        self.assertEqual((original/'reviewed').read_bytes(),b'old')
        self.assertEqual((original/'arrived-during-move').read_bytes(),b'new')

    def test_missing_native_primitive_fails_closed_without_path_fallback(self):
        original=self.source()
        with patch.object(recovery,'_WinHandle',side_effect=recovery.RecoveryError('API unavailable')):
            with self.assertRaises(recovery.RecoveryError):
                self.vault.probe_identity(original)
            item=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(item['status'],'failed')
        self.assertEqual(original.read_bytes(),b'original bytes')

    def test_postmove_verification_failure_returns_source_without_overwrite(self):
        original=self.source()
        real_probe=recovery._WindowsPinned.probe
        calls=[]
        def probe(pinned):
            calls.append(True)
            if len(calls)==3:
                raise recovery.RecoveryError('Injected post-move read failure')
            return real_probe(pinned)
        with patch.object(recovery._WindowsPinned,'probe',probe):
            item=self.vault.quarantine_path(self.sid,original)
        self.assertEqual(item['status'],'failed')
        self.assertEqual(original.read_bytes(),b'original bytes')
        self.assertFalse(self.payload(item).exists())

    def test_registry_export_backup_only_then_explicit_restore(self):
        with patch.object(recovery.subprocess,'run',side_effect=self.export) as run:
            item=self.vault.backup_registry(self.sid,r'HKCU\Software\FixtureApp')
        self.assertEqual(item['status'],'backed_up')
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0][1],'export')
        with patch.object(recovery.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            result=self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(result['status'],'restored')
        self.assertEqual(run.call_args.args[0][1],'import')

    def test_registry_nonzero_or_empty_export_cannot_be_success(self):
        for code in (0,5):
            with patch.object(recovery.subprocess,'run',return_value=subprocess.CompletedProcess([],code)):
                item=self.vault.backup_registry(self.sid,r'HKCU\Software\FixtureApp')
            self.assertEqual(item['status'],'failed')

    def test_registry_export_wrong_key_refused(self):
        def export(argv,**kwargs):
            Path(argv[3]).write_bytes(('Windows Registry Editor Version 5.00\n[HKEY_CURRENT_USER\\Software\\OtherApp]\n').encode('utf-16'))
            return subprocess.CompletedProcess(argv,0)
        with patch.object(recovery.subprocess,'run',side_effect=export):
            self.assertEqual(self.vault.backup_registry(self.sid,r'HKCU\Software\FixtureApp')['status'],'failed')

    def test_registry_backup_tampering_never_imported(self):
        with patch.object(recovery.subprocess,'run',side_effect=self.export):
            item=self.vault.backup_registry(self.sid,r'HKCU\Software\FixtureApp')
        self.payload(item).write_bytes(b'arbitrary registry data')
        with patch.object(recovery.subprocess,'run') as run:
            result=self.vault.restore(self.sid,item['item_id'])
        self.assertEqual(result['status'],'failed')
        run.assert_not_called()

    def test_shared_registry_roots_are_refused_without_subprocess(self):
        with patch.object(recovery.subprocess,'run') as run:
            for key in (r'HKCU\Software',r'HKLM\Software\Microsoft',r'HKLM\SYSTEM\Fixture',r'HKCU\Software\Policies\Fixture'):
                self.assertEqual(self.vault.backup_registry(self.sid,key)['status'],'failed')
        run.assert_not_called()


if __name__=='__main__':
    unittest.main()

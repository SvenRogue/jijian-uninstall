import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import scanner


class ScannerSafetyTests(unittest.TestCase):
    def test_exact_product_only_never_publisher_prefix_or_documents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            local, roaming, home = root/'Local', root/'Roaming', root/'User'
            for p in (local/'ExampleApp', local/'ExampleAppBackup', local/'SharedVendor',
                      roaming/'ExampleApp', home/'Documents'/'ExampleApp'):
                p.mkdir(parents=True)
            env = {'LOCALAPPDATA': str(local), 'APPDATA': str(roaming), 'USERPROFILE': str(home),
                   'ProgramData': str(root/'ProgramData')}
            with patch.dict(os.environ, env):
                paths = scanner._candidate_dirs(scanner.AppEntry('ExampleApp 1.2.3', publisher='SharedVendor'))
            self.assertEqual(set(paths), {str(local/'ExampleApp'), str(roaming/'ExampleApp')})

    def test_system_uninstaller_parent_is_not_an_install_directory(self):
        system = os.environ.get('SystemRoot', r'C:\Windows')
        entry = scanner.AppEntry('ExampleApp', uninstall_string=str(Path(system)/'System32'/'msiexec.exe'))
        with patch('app.scanner.os.path.isfile', return_value=True):
            self.assertEqual(scanner._derive_install_location(entry), '')

    def test_broad_roots_and_windowsapps_are_rejected(self):
        roots = [os.path.abspath(os.sep), os.environ.get('USERPROFILE', str(Path.home())),
                 os.environ.get('LOCALAPPDATA', str(Path.home())), r'C:\Program Files',
                 r'C:\ProgramData', r'C:\Windows\System32', r'C:\Program Files\WindowsApps\SomeApp']
        for path in roots:
            with self.subTest(path=path):
                self.assertFalse(scanner.path_is_safe(path))

    def test_missing_arp_registration_is_not_fabricated(self):
        entry = scanner.AppEntry('UninstalledExample')
        entry._arp_key = r'HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\UninstalledExample'
        with patch('app.scanner._reg_exists', return_value=False), patch('app.scanner._candidate_dirs', return_value=[]), patch('app.scanner._shortcut_paths', return_value=[]):
            self.assertEqual(scanner.inventory(entry).leftovers, [])

    def test_data_candidates_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td)/'ExampleApp'
            data.mkdir()
            entry = scanner.AppEntry('ExampleApp')
            with patch('app.scanner._candidate_dirs', return_value=[str(data)]), patch('app.scanner._reg_exists', return_value=False), patch('app.scanner._shortcut_paths', return_value=[]):
                items = scanner.inventory(entry).leftovers
            self.assertEqual(len(items), 1)
            self.assertFalse(items[0].checked)

    def test_symlink_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            target, link = Path(td)/'real', Path(td)/'link'
            target.mkdir()
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest('Windows symlink privilege unavailable')
            self.assertFalse(scanner.path_is_safe(str(link)))


if __name__ == '__main__':
    unittest.main()

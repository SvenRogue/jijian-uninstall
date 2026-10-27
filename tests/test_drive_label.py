import os
import unittest
from unittest.mock import patch

from app.drive_label import drive_label
from app.scanner import AppEntry


class DriveLabelTests(unittest.TestCase):
    def label(self, **fields):
        return drive_label(AppEntry('Example', **fields))

    def test_install_location_takes_precedence(self):
        self.assertEqual(self.label(install_location='"d:\\Apps\\Example"',
                                    display_icon='C:\\Other\\app.exe'), 'D:')
        self.assertEqual(self.label(install_location=r'\\server\share\app'), '网络位置')
        self.assertEqual(self.label(install_location='e:/Games/Example'), 'E:')

    def test_fallback_icon_and_uninstall_command(self):
        cases = [
            ({'display_icon': '"D:\\Program Files\\App\\app.exe",0'}, 'D:'),
            ({'display_icon': r'E:\Apps\app.exe,-1'}, 'E:'),
            ({'uninstall_string': '"F:\\Program Files\\App\\uninstall.exe" /S'}, 'F:'),
            ({'uninstall_string': r'G:\App\uninstall.exe /S'}, 'G:'),
            ({'quiet_uninstall_string': r'\\server\share\app\remove.exe /S'}, '网络位置'),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.assertEqual(self.label(**fields), expected)

    def test_environment_variables_are_case_insensitive(self):
        with patch.dict(os.environ, {'APP_HOME': r'F:\Apps', 'SystemRoot': r'D:\Windows'}, clear=True):
            self.assertEqual(self.label(install_location=r'%app_home%\Example'), 'F:')
            self.assertEqual(self.label(display_icon=r'%APP_HOME%\example.exe,0'), 'F:')
            self.assertEqual(self.label(uninstall_string=r'%systemroot%\System32\msiexec.exe /x test'), '位置未知')
            self.assertEqual(self.label(display_icon=r'%SystemRoot%\explorer.exe'), '位置未知')

    def test_system_executables_do_not_supply_location(self):
        for value in (r'C:\Windows\System32\msiexec.exe /x {abc}',
                      r'D:\Windows\System32\rundll32.exe foo.dll,Remove',
                      r'C:\Windows\explorer.exe', r'D:\Other\msiexec.exe /x abc',
                      'msiexec.exe /x {abc}'):
            with self.subTest(value=value):
                self.assertEqual(self.label(uninstall_string=value), '位置未知')
        self.assertEqual(self.label(display_icon=r'C:\Windows\System32\shell32.exe,1',
                                    uninstall_string=r'D:\Apps\remove.exe'), 'D:')

    def test_unknown_and_ambiguous_paths(self):
        for fields in ({}, {'install_location': r'C:relative'},
                       {'install_location': r'\rooted'}, {'install_location': r'\\server'},
                       {'install_location': r'%MISSING_VAR%\App'},
                       {'uninstall_string': r'C:\Program Files\App\uninstall.exe /S'},
                       {'uninstall_string': '"D:\\App\\uninstall.exe /S'},
                       {'display_icon': r'C:\App\app.dll,0'},
                       {'install_location': r'\\?\C:\App'}):
            with self.subTest(fields=fields):
                self.assertEqual(self.label(**fields), '位置未知')

    def test_invalid_install_location_allows_fallback(self):
        self.assertEqual(self.label(install_location='unknown',
                                    uninstall_string=r'Z:\App\remove.exe'), 'Z:')


if __name__ == '__main__':
    unittest.main()

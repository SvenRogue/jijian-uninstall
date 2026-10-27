import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import icons, locations
from app.scanner import AppEntry

class IconsLocationsTests(unittest.TestCase):
    def test_parse_resource_indices_and_commas(self):
        self.assertEqual(icons.parse_display_icon('"C:\\Program Files\\A,B\\app.exe",-2'),('C:\\Program Files\\A,B\\app.exe',-2))
        self.assertEqual(icons.parse_display_icon('C:\\Apps\\app.exe,3'),('C:\\Apps\\app.exe',3))
    def test_never_use_folder_as_icon(self):
        with tempfile.TemporaryDirectory() as td:
            e=AppEntry('Demo',display_icon=td,install_location=td)
            self.assertEqual(icons.icon_candidates(e),[])
    def test_exclude_uninstaller_and_prefer_product(self):
        with tempfile.TemporaryDirectory() as td:
            for n in ('uninstall.exe','update.exe','Demo.exe','other.exe'):
                Path(td,n).write_bytes(b'')
            e=AppEntry('Demo',install_location=td)
            paths=icons.icon_candidates(e)
            self.assertEqual(Path(paths[0][0]).name,'Demo.exe')
            self.assertNotIn('uninstall.exe',[Path(p).name for p,_ in paths])
    def test_open_existing_registered_directory(self):
        with tempfile.TemporaryDirectory() as td:
            p,reason=locations.resolve_location(AppEntry('Example',install_location=td))
            self.assertEqual(os.path.normcase(p),os.path.normcase(td))
            self.assertEqual(reason,'安装登记')
    def test_missing_location_is_disabled(self):
        self.assertEqual(locations.resolve_location(AppEntry('Example')),('', '没有可确认的安装位置'))

if __name__ == '__main__': unittest.main()

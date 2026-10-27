import unittest
from app.ui import sort_apps
from app.scanner import AppEntry, LeftoverItem

class SortingTests(unittest.TestCase):
    def setUp(self):
        self.a=AppEntry('Alpha',size=20,publisher='Zed',install_date='20260101')
        self.b=AppEntry('beta',size=100,publisher='Acme',install_date='20261001')
        self.c=AppEntry('Gamma',size=0,publisher='',install_date='')
        self.a.leftovers=[LeftoverItem('dir','x',size=999999)]
        self.apps=[self.c,self.b,self.a]
    def test_name_directions(self):
        self.assertEqual([a.name for a in sort_apps(self.apps,'name')],['Alpha','beta','Gamma'])
        self.assertEqual([a.name for a in sort_apps(self.apps,'name_desc')],['Gamma','beta','Alpha'])
    def test_installed_size_and_unknown_last(self):
        self.assertEqual([a.name for a in sort_apps(self.apps,'size')],['beta','Alpha','Gamma'])
        self.assertEqual([a.name for a in sort_apps(self.apps,'size_asc')],['Alpha','beta','Gamma'])
    def test_date_and_publisher(self):
        self.assertEqual([a.name for a in sort_apps(self.apps,'date')],['beta','Alpha','Gamma'])
        self.assertEqual(sort_apps(self.apps,'publisher')[0].name,'Gamma')
    def test_unknown_key_defaults_to_name(self):
        self.assertEqual(sort_apps(self.apps,'unexpected')[0].name,'Alpha')

if __name__ == '__main__': unittest.main()

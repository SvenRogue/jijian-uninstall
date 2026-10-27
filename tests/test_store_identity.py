import unittest

from app import scanner


class StoreIdentityTests(unittest.TestCase):
    def test_manifest_identity_and_logo(self):
        rows = "Vendor.Product\tVendor.Product_abcd\t1.2\tVendor\tC:\\Apps\\Product\t真实名称\tC:\\Apps\\Product\\logo.png\n"
        app, = scanner._parse_store_lines(rows)
        self.assertEqual(app.name, "真实名称")
        self.assertTrue(app.display_icon.endswith("logo.png"))
        self.assertEqual(app.uid, "store:Vendor.Product_abcd")
        self.assertEqual(app._pkg_family, "Vendor.Product_abcd")
        self.assertEqual(app._pkg_full, "Vendor.Product")

    def test_fallback_uses_exact_package_name_and_preserves_filter(self):
        rows = ("Vendor.ProductApp\tVendor.ProductApp_abcd\t1\tVendor\tC:\\Apps\n"
                "Microsoft.VCLibs\tMicrosoft.VCLibs_abcd\t1\tMicrosoft\tC:\\Apps\n"
                "Vendor.Other\tVendor.Other_abcd\t1\tVendor\tC:\\Apps\tms-resource:Name\t\n")
        apps = scanner._parse_store_lines(rows)
        self.assertEqual([app.name for app in apps], ["Vendor.ProductApp", "Vendor.Other"])
        self.assertEqual([app._pkg_family for app in apps], ["Vendor.ProductApp_abcd", "Vendor.Other_abcd"])
        self.assertTrue(all(not app.display_icon for app in apps))

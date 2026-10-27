"""Isolated UI system tests: tokens, appearance switch, chrome widgets.

No application is scanned, uninstalled or deleted here.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app import theme


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def tearDown(self):
        theme.set_mode("light")

    def test_both_appearances_produce_complete_stylesheets(self):
        for mode in theme.MODES:
            qss = theme.app_qss(mode)
            with self.subTest(mode=mode):
                self.assertGreater(len(qss), 3000)
                self.assertIn(theme.palette(mode)["accent"], qss)
                # fractional px font sizes are silently dropped by Qt
                for line in qss.splitlines():
                    if "font-size" in line:
                        self.assertNotIn(".", line.split("font-size")[1].split(";")[0],
                                         f"fractional font size in {mode}: {line.strip()}")

    def test_palette_tokens_are_distinct_and_complete(self):
        required = {"window", "sidebar", "content", "card", "text", "text2", "text3",
                    "accent", "on_accent", "danger", "warn", "success", "sep", "border"}
        for mode in theme.MODES:
            c = theme.palette(mode)
            with self.subTest(mode=mode):
                self.assertTrue(required.issubset(c))
                self.assertNotEqual(c["text"].lower(), c["content"].lower())

    def test_dialog_stylesheet_covers_tree_and_steps(self):
        for mode in theme.MODES:
            qss = theme.dialog_qss(mode)
            with self.subTest(mode=mode):
                for token in ("QTreeWidget", "QHeaderView", "QLabel#Step", "QComboBox"):
                    self.assertIn(token, qss)

    def test_set_mode_rejects_unknown_values(self):
        theme.set_mode("dark")
        self.assertEqual(theme.set_mode("purple"), "dark")
        self.assertEqual(theme.current_mode(), "dark")
        self.assertEqual(theme.set_mode("light"), "light")

    def test_apply_palette_sets_native_colors(self):
        from PyQt5.QtGui import QPalette
        theme.apply_palette(self.qt, "dark")
        pal = self.qt.palette()
        self.assertEqual(pal.color(QPalette.Window).name().lower(),
                         theme.palette("dark")["window"].lower())
        self.assertEqual(pal.color(QPalette.Highlight).name().lower(),
                         theme.palette("dark")["accent"].lower())
        theme.apply_palette(self.qt, "light")
        self.assertEqual(self.qt.palette().color(QPalette.Window).name().lower(),
                         theme.palette("light")["window"].lower())


class ChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_segmented_control_is_exclusive(self):
        from app.chrome import SegmentedControl
        seen = []
        seg = SegmentedControl((("all", "全部"), ("store", "商店")))
        seg.changed.connect(seen.append)
        seg.set_value("store", emit=True)
        self.assertEqual(seg.value(), "store")
        self.assertEqual(seen, ["store"])
        checked = [k for k, b in seg._buttons.items() if b.isChecked()]
        self.assertEqual(checked, ["store"])
        seg.deleteLater()

    def test_traffic_lights_emit_actions(self):
        from app.chrome import TrafficLights
        lights = TrafficLights()
        fired = []
        lights.close_clicked.connect(lambda: fired.append("close"))
        lights.min_clicked.connect(lambda: fired.append("min"))
        lights.max_clicked.connect(lambda: fired.append("max"))
        buttons = [b for b in lights.children() if b.__class__.__name__ == "QPushButton"]
        self.assertEqual(len(buttons), 3)
        for b in buttons:
            b.click()
        self.assertEqual(fired, ["close", "min", "max"])
        lights.deleteLater()

    def test_card_marks_last_row_without_border(self):
        from app.chrome import Card
        card = Card("分组")
        from PyQt5.QtWidgets import QLabel
        first = card.add(QLabel("a"))
        last = card.add(QLabel("b"), last=True)
        self.assertEqual(first.property("last"), "false")
        self.assertEqual(last.property("last"), "true")
        card.deleteLater()


if __name__ == "__main__":
    unittest.main()

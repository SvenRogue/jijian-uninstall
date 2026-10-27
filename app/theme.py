"""Apple-style design system for 极简卸载.

One token set, two appearances. Light follows macOS System Settings (white
cards on #F5F5F7, hairline separators, system blue); dark follows the same
structure on system grays. All sizes are logical px at 96 DPI.
"""
from __future__ import annotations

LIGHT = {
    "name": "light",
    "window": "#ECECEE",
    "sidebar": "#F2F2F5",
    "content": "#FFFFFF",
    "card": "#F7F7F9",
    "row": "#FFFFFF",
    "row_hover": "#F0F0F3",
    "field": "#FFFFFF",
    "track": "#E9E9ED",
    "seg_selected": "#FFFFFF",
    "seg_text": "#3C3C43",
    "text": "#1D1D1F",
    "text2": "#6E6E73",
    "text3": "#98989D",
    "sep": "rgba(60,60,67,0.11)",
    "border": "rgba(0,0,0,0.10)",
    "accent": "#007AFF",
    "accent_hi": "#3395FF",
    "accent_soft": "rgba(0,122,255,0.11)",
    "on_accent": "#FFFFFF",
    "danger": "#FF3B30",
    "warn": "#FF9500",
    "success": "#34C759",
    "shadow": "rgba(0,0,0,0.20)",
    "log": "#FBFBFD",
    "log_text": "#52525A",
    "selection": "#007AFF",
}

DARK = {
    "name": "dark",
    "window": "#1C1C1E",
    "sidebar": "#232326",
    "content": "#1C1C1E",
    "card": "#2C2C2E",
    "row": "#2C2C2E",
    "row_hover": "#3A3A3C",
    "field": "#2C2C2E",
    "track": "#3A3A3C",
    "seg_selected": "#636366",
    "seg_text": "#EBEBF5",
    "text": "#F5F5F7",
    "text2": "#A1A1A6",
    "text3": "#7C7C82",
    "sep": "rgba(255,255,255,0.10)",
    "border": "rgba(255,255,255,0.13)",
    "accent": "#0A84FF",
    "accent_hi": "#409CFF",
    "accent_soft": "rgba(10,132,255,0.20)",
    "on_accent": "#FFFFFF",
    "danger": "#FF453A",
    "warn": "#FF9F0A",
    "success": "#30D158",
    "shadow": "rgba(0,0,0,0.55)",
    "log": "#161618",
    "log_text": "#A1A1A6",
    "selection": "#0A84FF",
}

MODES = ("light", "dark")
_mode = "light"


def set_mode(mode: str) -> str:
    global _mode
    if mode in MODES:
        _mode = mode
    return _mode


def current_mode() -> str:
    return _mode


def palette(mode: str | None = None) -> dict:
    return DARK if (mode or _mode) == "dark" else LIGHT


def font_family() -> str:
    """Segoe UI Variable ships with Windows 11; YaHei keeps CJK crisp."""
    return ("Segoe UI Variable Display, Segoe UI Variable Text, Segoe UI, "
            "Microsoft YaHei UI, Microsoft YaHei, sans-serif")


def mono_family() -> str:
    return "Cascadia Mono, Consolas, Microsoft YaHei UI, monospace"


def apply_palette(app, mode: str | None = None) -> None:
    """Give native widgets (scroll viewports, menus, message boxes) the same
    colours as the stylesheet, so nothing falls back to a white system surface."""
    from PyQt5.QtGui import QColor, QPalette
    c = palette(mode)
    app.setStyleSheet(app_qss(mode))
    pal = QPalette()
    window, base, text = QColor(c["window"]), QColor(c["content"]), QColor(c["text"])
    pal.setColor(QPalette.Window, window)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, QColor(c["card"]))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(c["card"]))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.ToolTipBase, QColor(c["text"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["content"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["on_accent"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["text3"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["text3"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["text3"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(c["text3"]))
    app.setPalette(pal)


def app_qss(mode: str | None = None) -> str:
    c = palette(mode)
    f, m = font_family(), mono_family()
    return f"""
* {{
    font-family: "{f}";
    outline: none;
}}
QWidget {{
    color: {c['text']};
}}
QWidget#Root, QWidget#Shell {{
    background: transparent;
}}
QWidget#Shell {{
    background: {c['window']};
    border: 1px solid {c['border']};
    border-radius: 13px;
}}
QWidget#Sidebar {{
    background: {c['sidebar']};
    border-top-left-radius: 13px;
    border-bottom-left-radius: 13px;
}}
QWidget#Content {{
    background: {c['content']};
    border-top-right-radius: 13px;
    border-bottom-right-radius: 13px;
}}
QWidget#TitleBar {{
    background: transparent;
}}

/* ------------------------------------------------------------- type scale */
QLabel {{ background: transparent; color: {c['text']}; }}
QLabel[role="title"]     {{ font-size: 13px; font-weight: 600; }}
QLabel[role="h1"]        {{ font-size: 23px; font-weight: 700; }}
QLabel[role="h2"]        {{ font-size: 13px; font-weight: 600; }}
QLabel[role="sub"]       {{ color: {c['text2']}; font-size: 12px; }}
QLabel[role="faint"]     {{ color: {c['text3']}; font-size: 11px; }}
QLabel[role="section"]   {{ color: {c['text2']}; font-size: 11px; font-weight: 600;
                            padding-left: 2px; }}
QLabel[role="meta"]      {{ color: {c['text2']}; font-size: 12px; }}
QLabel[role="rowname"]   {{ font-size: 12px; }}
QLabel[role="rownote"]   {{ color: {c['text3']}; font-size: 11px; }}
QLabel[role="size"]      {{ color: {c['text2']}; font-size: 11px; }}

/* ------------------------------------------------------------- traffic lights */
QPushButton#Traffic {{
    border: none; border-radius: 6px; min-width: 12px; max-width: 12px;
    min-height: 12px; max-height: 12px; padding: 0; color: transparent;
    font-size: 9px; font-weight: 700;
}}
QPushButton#Traffic[light="close"] {{ background: #FF5F57; }}
QPushButton#Traffic[light="min"]   {{ background: #FEBC2E; }}
QPushButton#Traffic[light="max"]   {{ background: #28C840; }}
QPushButton#Traffic:hover {{ color: rgba(0,0,0,0.55); }}

/* ------------------------------------------------------------- search */
QLineEdit#Search {{
    background: {c['field']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 6px 10px 6px 28px;
    color: {c['text']};
    font-size: 12px;
    selection-background-color: {c['selection']};
    selection-color: white;
}}
QLineEdit#Search:focus {{ border: 1px solid {c['accent']}; }}

/* ------------------------------------------------------------- segmented control */
QWidget#Segment {{
    background: {c['track']};
    border-radius: 7px;
}}
QPushButton#SegmentItem {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    color: {c['seg_text']};
    font-size: 11px;
}}
QPushButton#SegmentItem:hover {{ color: {c['text']}; }}
QPushButton#SegmentItem:checked {{
    background: {c['seg_selected']};
    color: {c['text']};
    font-weight: 600;
    border: 1px solid {c['border']};
}}

/* ------------------------------------------------------------- buttons */
QPushButton#Primary {{
    background: {c['accent']};
    border: none; border-radius: 7px;
    padding: 7px 18px;
    color: {c['on_accent']};
    font-size: 12px; font-weight: 600;
}}
QPushButton#Primary:hover  {{ background: {c['accent_hi']}; }}
QPushButton#Primary:pressed {{ background: {c['accent']}; }}
QPushButton#Primary:disabled {{ background: {c['track']}; color: {c['text3']}; }}

QPushButton#Secondary {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 7px; padding: 7px 16px;
    color: {c['text']}; font-size: 12px;
}}
QPushButton#Secondary:hover {{ background: {c['row_hover']}; }}
QPushButton#Secondary:disabled {{ color: {c['text3']}; }}

QPushButton#Pill {{
    background: transparent;
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px 10px;
    color: {c['text2']};
    font-size: 11px;
}}
QPushButton#Pill:hover {{ background: {c['row_hover']}; color: {c['text']}; }}
QPushButton#Pill:checked {{
    background: {c['accent_soft']}; border-color: transparent; color: {c['accent']};
}}

QPushButton#SidebarItem {{
    background: transparent; border: none; border-radius: 7px;
    padding: 7px 10px; text-align: left;
    color: {c['text']}; font-size: 12px;
}}
QPushButton#SidebarItem:hover {{ background: {c['row_hover']}; }}

QPushButton#Danger {{
    background: rgba(255,59,48,0.12);
    border: none; border-radius: 7px; padding: 7px 16px;
    color: {c['danger']}; font-size: 12px; font-weight: 600;
}}
QPushButton#Danger:hover {{ background: rgba(255,59,48,0.20); }}

QPushButton#Link {{
    background: transparent; border: none; padding: 2px;
    color: {c['accent']}; font-size: 11px;
}}
QPushButton#Link:hover {{ color: {c['accent_hi']}; }}

/* ------------------------------------------------------------- app list */
QListWidget#AppList {{
    background: transparent; border: none; padding: 0;
}}
QListWidget#AppList::item {{
    background: transparent; border: none; margin: 1px 0; padding: 0;
}}
QListWidget#AppList::item:hover {{ background: transparent; }}
QListWidget#AppList::item:selected {{ background: transparent; }}

/* ------------------------------------------------------------- cards */
QFrame#Card {{
    background: {c['card']};
    border: none;
    border-radius: 10px;
}}
QFrame#CardRow {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {c['sep']};
}}
QFrame#CardRow[last="true"] {{ border-bottom: none; }}
QFrame#Divider {{ background: {c['sep']}; border: none; max-height: 1px; }}
QFrame#HeaderCard {{
    background: transparent; border: none;
}}

/* ------------------------------------------------------------- log */
QPlainTextEdit#Log {{
    background: {c['log']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    color: {c['log_text']};
    font-family: "{m}";
    font-size: 11px;
    padding: 8px 10px;
    selection-background-color: {c['selection']};
}}
QPlainTextEdit#Log QScrollBar:vertical {{ background: transparent; }}

/* ------------------------------------------------------------- progress */
QProgressBar {{
    background: {c['track']};
    border: none; border-radius: 2px; height: 4px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 2px;
    background: {c['accent']};
}}

/* ------------------------------------------------------------- checkbox */
QCheckBox {{ color: {c['text2']}; font-size: 12px; spacing: 6px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {c['border']};
    background: {c['field']};
}}
QCheckBox::indicator:checked {{
    background: {c['accent']}; border: 1px solid {c['accent']};
    image: none;
}}
QCheckBox::indicator:disabled {{ background: {c['track']}; }}

/* ------------------------------------------------------------- scrollbar */
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 2px 1px;
}}
QScrollBar::handle:vertical {{
    background: rgba(120,120,128,0.32); border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(120,120,128,0.55); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#ScrollBody {{ background: transparent; }}

/* ------------------------------------------------------------- tooltip */
QToolTip {{
    background: {c['text']}; color: {c['content']};
    border: none; border-radius: 6px; padding: 5px 8px; font-size: 11px;
}}

/* ------------------------------------------------------------- menus */
QMenu {{
    background: {c['content']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c['accent']}; color: white; }}
"""


def dialog_qss(mode: str | None = None) -> str:
    """Shared styling for the uninstall wizard and recovery center."""
    c = palette(mode)
    return app_qss(mode) + f"""
QDialog {{ background: {c['content']}; }}
QWidget#DialogShell {{ background: {c['content']}; border-radius: 13px; }}
QLabel#Step {{
    background: {c['card']};
    border-radius: 8px;
    padding: 8px 10px;
    color: {c['text3']};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#Step[active="true"] {{
    background: {c['accent_soft']};
    color: {c['accent']};
}}
QComboBox {{
    background: {c['field']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 6px;
    padding: 5px 10px; min-width: 96px; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {c['content']}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['accent']};
    selection-color: white;
    outline: none;
}}
QTreeWidget {{
    background: {c['card']}; color: {c['text']};
    border: none; border-radius: 10px;
    alternate-background-color: transparent;
    font-size: 12px;
}}
QTreeWidget::item {{ padding: 5px 2px; border-bottom: 1px solid {c['sep']}; }}
QTreeWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QHeaderView::section {{
    background: transparent; color: {c['text3']};
    border: none; border-bottom: 1px solid {c['sep']};
    padding: 7px 4px; font-size: 11px; font-weight: 600;
}}
QMessageBox {{ background: {c['content']}; }}
"""

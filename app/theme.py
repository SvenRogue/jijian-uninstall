"""ChatGPT desktop design system for 极简卸载.

Structure follows the ChatGPT Windows app: a flat left rail on a slightly
darker surface, a large content canvas, generous whitespace, one accent colour
and pill-shaped primary actions. Two appearances (light / dark) share the same
token names so every widget is written once.

All sizes are logical px at 96 DPI; Windows scaling is handled by Qt.
"""
from __future__ import annotations

LIGHT = {
    "name": "light",
    "window": "#FFFFFF",
    "sidebar": "#F9F9F9",
    "content": "#FFFFFF",
    "card": "#F7F7F8",
    "row": "#FFFFFF",
    "row_hover": "#ECECF1",
    "field": "#F4F4F4",
    "track": "#E5E5E5",
    "seg_selected": "#FFFFFF",
    "seg_text": "#5D5D5D",
    "text": "#0D0D0D",
    "text2": "#5D5D5D",
    "text3": "#8F8F8F",
    "sep": "rgba(13,13,13,0.10)",
    "border": "rgba(13,13,13,0.12)",
    "accent": "#0D0D0D",          # ChatGPT's primary action is near-black
    "accent_hi": "#2F2F2F",
    "accent_soft": "rgba(13,13,13,0.06)",
    "on_accent": "#FFFFFF",
    "link": "#0B6E4F",
    "danger": "#D93025",
    "warn": "#B26B00",
    "success": "#0B6E4F",
    "shadow": "rgba(0,0,0,0.16)",
    "log": "#FAFAFA",
    "log_text": "#4A4A4A",
    "selection": "#0D0D0D",
    "scroll": "rgba(13,13,13,0.22)",
    "scroll_hover": "rgba(13,13,13,0.38)",
}

DARK = {
    "name": "dark",
    "window": "#212121",
    "sidebar": "#171717",
    "content": "#212121",
    "card": "#2A2A2A",
    "row": "#2A2A2A",
    "row_hover": "#303030",
    "field": "#2F2F2F",
    "track": "#3A3A3A",
    "seg_selected": "#4A4A4A",
    "seg_text": "#C7C7C7",
    "text": "#ECECEC",
    "text2": "#B4B4B4",
    "text3": "#8E8E8E",
    "sep": "rgba(255,255,255,0.10)",
    "border": "rgba(255,255,255,0.14)",
    "accent": "#FFFFFF",          # ChatGPT dark primary is white on dark
    "accent_hi": "#E3E3E3",
    "accent_soft": "rgba(255,255,255,0.08)",
    "on_accent": "#0D0D0D",
    "link": "#7BD9B0",
    "danger": "#FF7A70",
    "warn": "#E8B25C",
    "success": "#7BD9B0",
    "shadow": "rgba(0,0,0,0.50)",
    "log": "#1A1A1A",
    "log_text": "#B4B4B4",
    "selection": "#FFFFFF",
    "scroll": "rgba(255,255,255,0.20)",
    "scroll_hover": "rgba(255,255,255,0.34)",
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
    """ChatGPT ships a neutral grotesque; Segoe UI Variable is the closest
    system equivalent, with YaHei keeping CJK crisp."""
    return ("Segoe UI Variable Text, Segoe UI Variable Display, Segoe UI, "
            "Microsoft YaHei UI, Microsoft YaHei, sans-serif")


def mono_family() -> str:
    return "Cascadia Mono, Consolas, Microsoft YaHei UI, monospace"


def apply_palette(app, mode: str | None = None) -> None:
    """Apply stylesheet *and* a matching native palette.

    Qt paints some native surfaces (scroll viewports, menus, message boxes)
    from the palette rather than the stylesheet; without this they stay white
    in dark mode.
    """
    from PyQt5.QtGui import QColor, QPalette
    c = palette(mode)
    app.setStyleSheet(app_qss(mode))
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["window"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["content"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["card"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["card"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["text"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["window"]))
    pal.setColor(QPalette.Highlight, QColor(c["selection"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["on_accent"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["text3"]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor(c["text3"]))
    app.setPalette(pal)


def app_qss(mode: str | None = None) -> str:
    c = palette(mode)
    f, m = font_family(), mono_family()
    return f"""
* {{
    font-family: "{f}";
    outline: none;
}}
QWidget {{ color: {c['text']}; }}
QWidget#Root, QWidget#Shell {{ background: transparent; }}
QWidget#Shell {{ background: {c['window']}; }}
QWidget#Sidebar {{ background: {c['sidebar']}; }}
QWidget#Content {{ background: {c['content']}; }}

/* ------------------------------------------------------------- type scale */
QLabel {{ background: transparent; color: {c['text']}; }}
QLabel[role="title"]   {{ font-size: 13px; font-weight: 600; }}
QLabel[role="h1"]      {{ font-size: 22px; font-weight: 600; }}
QLabel[role="h2"]      {{ font-size: 14px; font-weight: 600; }}
QLabel[role="sub"]     {{ color: {c['text2']}; font-size: 12px; }}
QLabel[role="faint"]   {{ color: {c['text3']}; font-size: 11px; }}
QLabel[role="section"] {{ color: {c['text2']}; font-size: 11px; font-weight: 600; }}
QLabel[role="meta"]    {{ color: {c['text2']}; font-size: 12px; }}
QLabel[role="rowname"] {{ font-size: 12px; }}
QLabel[role="rownote"] {{ color: {c['text3']}; font-size: 11px; }}
QLabel[role="size"]    {{ color: {c['text2']}; font-size: 11px; }}

/* ------------------------------------------------------------- search */
QLineEdit#Search {{
    background: {c['field']};
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 7px 10px 7px 28px;
    color: {c['text']};
    font-size: 12px;
    selection-background-color: {c['selection']};
    selection-color: {c['on_accent']};
}}
QLineEdit#Search:hover {{ background: {c['row_hover']}; }}
QLineEdit#Search:focus {{ border: 1px solid {c['border']}; background: {c['field']}; }}

/* ------------------------------------------------------------- segmented */
QWidget#Segment {{ background: {c['track']}; border-radius: 8px; }}
QPushButton#SegmentItem {{
    background: transparent; border: none; border-radius: 7px;
    padding: 4px 9px; color: {c['seg_text']}; font-size: 11px;
}}
QPushButton#SegmentItem:hover {{ color: {c['text']}; }}
QPushButton#SegmentItem:checked {{
    background: {c['seg_selected']}; color: {c['text']}; font-weight: 600;
}}

/* ------------------------------------------------------------- buttons */
QPushButton#Primary {{
    background: {c['accent']}; border: none; border-radius: 17px;
    padding: 8px 20px; color: {c['on_accent']};
    font-size: 12px; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {c['accent_hi']}; }}
QPushButton#Primary:disabled {{ background: {c['track']}; color: {c['text3']}; }}

QPushButton#Secondary {{
    background: transparent; border: 1px solid {c['border']};
    border-radius: 17px; padding: 7px 16px;
    color: {c['text']}; font-size: 12px;
}}
QPushButton#Secondary:hover {{ background: {c['row_hover']}; }}
QPushButton#Secondary:disabled {{ color: {c['text3']}; border-color: {c['sep']}; }}

QPushButton#Pill {{
    background: transparent; border: 1px solid {c['border']};
    border-radius: 15px; padding: 5px 12px;
    color: {c['text2']}; font-size: 11px;
}}
QPushButton#Pill:hover {{ background: {c['row_hover']}; color: {c['text']}; }}
QPushButton#Pill:checked {{ background: {c['accent']}; color: {c['on_accent']}; border-color: transparent; }}

QPushButton#SidebarItem {{
    background: transparent; border: none; border-radius: 8px;
    padding: 7px 9px; text-align: left;
    color: {c['text']}; font-size: 12px;
}}
QPushButton#SidebarItem:hover {{ background: {c['row_hover']}; }}

QPushButton#Danger {{
    background: transparent; border: 1px solid {c['border']};
    border-radius: 17px; padding: 7px 16px;
    color: {c['danger']}; font-size: 12px; font-weight: 600;
}}
QPushButton#Danger:hover {{ background: {c['row_hover']}; }}

QPushButton#Link {{
    background: transparent; border: none; padding: 2px;
    color: {c['text2']}; font-size: 11px; text-align: left;
}}
QPushButton#Link:hover {{ color: {c['text']}; }}

/* ------------------------------------------------------------- app list */
QListWidget#AppList {{ background: transparent; border: none; padding: 0; }}
QListWidget#AppList::item {{ background: transparent; border: none; padding: 0; }}
QListWidget#AppList::item:hover {{ background: transparent; }}
QListWidget#AppList::item:selected {{ background: transparent; }}

/* ------------------------------------------------------------- cards */
QFrame#Card {{ background: {c['card']}; border: none; border-radius: 12px; }}
QFrame#CardRow {{ background: transparent; border: none; border-bottom: 1px solid {c['sep']}; }}
QFrame#CardRow[last="true"] {{ border-bottom: none; }}
QFrame#Divider {{ background: {c['sep']}; border: none; max-height: 1px; }}

/* ------------------------------------------------------------- log */
QPlainTextEdit#Log {{
    background: {c['log']}; border: 1px solid {c['sep']};
    border-radius: 10px; color: {c['log_text']};
    font-family: "{m}"; font-size: 11px; padding: 8px 10px;
    selection-background-color: {c['selection']};
    selection-color: {c['on_accent']};
}}
QPlainTextEdit#Log QScrollBar:vertical {{ background: transparent; }}

/* ------------------------------------------------------------- progress */
QProgressBar {{
    background: {c['track']}; border: none; border-radius: 2px;
    height: 3px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ border-radius: 2px; background: {c['accent']}; }}

/* ------------------------------------------------------------- checkbox */
QCheckBox {{ color: {c['text2']}; font-size: 12px; spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {c['border']}; background: transparent;
}}
QCheckBox::indicator:hover {{ border-color: {c['text2']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}

/* ------------------------------------------------------------- scrollbars */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 1px; }}
QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#ScrollBody {{ background: transparent; }}

/* ------------------------------------------------------------- misc */
QToolTip {{
    background: {c['text']}; color: {c['window']};
    border: none; border-radius: 6px; padding: 5px 8px; font-size: 11px;
}}
QMenu {{
    background: {c['content']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 10px; padding: 5px;
}}
QMenu::item {{ padding: 6px 18px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['row_hover']}; }}
QMenu::separator {{ height: 1px; background: {c['sep']}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; }}
"""


def dialog_qss(mode: str | None = None) -> str:
    """Shared styling for the uninstall wizard and recovery center."""
    c = palette(mode)
    return app_qss(mode) + f"""
QDialog {{ background: {c['window']}; }}
QLabel#Step {{
    background: transparent; border-radius: 8px; padding: 7px 10px;
    color: {c['text3']}; font-size: 11px; font-weight: 600;
    border: 1px solid {c['sep']};
}}
QLabel#Step[active="true"] {{
    background: {c['accent_soft']}; color: {c['text']};
    border: 1px solid {c['border']};
}}
QComboBox {{
    background: {c['field']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 8px;
    padding: 5px 10px; min-width: 92px; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {c['content']}; color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {c['row_hover']};
    selection-color: {c['text']};
    outline: none;
}}
QTreeWidget {{
    background: {c['card']}; color: {c['text']};
    border: none; border-radius: 12px;
    alternate-background-color: transparent; font-size: 12px;
}}
QTreeWidget::item {{ padding: 5px 2px; border-bottom: 1px solid {c['sep']}; }}
QTreeWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QHeaderView::section {{
    background: transparent; color: {c['text3']};
    border: none; border-bottom: 1px solid {c['sep']};
    padding: 7px 4px; font-size: 11px; font-weight: 600;
}}
QMessageBox {{ background: {c['window']}; }}
"""

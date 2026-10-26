"""Design system for 极简卸载 (JiJian Uninstall).

Dark glassmorphism, one accent colour, generous spacing.
All sizes in logical px at 96 DPI; Windows scaling is handled by Qt.
"""
from __future__ import annotations

# ---------------------------------------------------------------- palette
BG0 = "#0B0D12"          # app background (top)
BG1 = "#12151C"          # app background (bottom)
SURFACE = "rgba(255,255,255,0.045)"
SURFACE_HOVER = "rgba(255,255,255,0.085)"
SURFACE_ACTIVE = "rgba(108,140,255,0.16)"
BORDER = "rgba(255,255,255,0.085)"
BORDER_STRONG = "rgba(255,255,255,0.16)"

ACCENT = "#6C8CFF"       # primary blue-violet
ACCENT_HI = "#8AA3FF"
ACCENT_DIM = "#3F55A8"
SUCCESS = "#3DDC97"
WARN = "#FFB454"
DANGER = "#FF5C6C"

TEXT = "#E8EBF2"
TEXT_DIM = "#98A0B4"
TEXT_FAINT = "#5E6577"

RADIUS = 12
RADIUS_LG = 16


def font_family() -> str:
    """Best available CJK-capable UI font on this host."""
    return "Microsoft YaHei UI, Segoe UI, Microsoft YaHei, sans-serif"


# ---------------------------------------------------------------- qss
def app_qss() -> str:
    f = font_family()
    return f"""
* {{
    font-family: "{f}";
    outline: none;
}}
QWidget#Root {{
    background: transparent;
}}
QWidget#Shell {{
    background: qlineargradient(x1:0, y1:0, x2:0.25, y2:1,
                stop:0 {BG0}, stop:0.55 {BG1}, stop:1 #0A0C11);
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG}px;
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel[role="title"]  {{ font-size: 15px; font-weight: 600; letter-spacing: 0.3px; }}
QLabel[role="sub"]    {{ color: {TEXT_DIM}; font-size: 12px; }}
QLabel[role="faint"]  {{ color: {TEXT_FAINT}; font-size: 11px; }}
QLabel[role="h1"]     {{ font-size: 21px; font-weight: 700; letter-spacing: 0.4px; }}
QLabel[role="h2"]     {{ font-size: 13px; font-weight: 600; color: {TEXT_DIM}; letter-spacing: 0.6px; }}

/* ---------------------------------------------------------- window buttons */
QPushButton#WinBtn {{
    background: transparent; border: none; border-radius: 7px;
    color: {TEXT_DIM}; font-size: 15px;
    min-width: 30px; max-width: 30px; min-height: 28px; max-height: 28px;
}}
QPushButton#WinBtn:hover  {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#WinBtn#Close:hover {{ background: {DANGER}; color: white; }}

/* ---------------------------------------------------------- search box */
QLineEdit#Search {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 9px 14px 9px 36px;
    color: {TEXT};
    font-size: 13px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit#Search:focus {{ border: 1px solid {ACCENT}; background: rgba(108,140,255,0.07); }}

/* ---------------------------------------------------------- pill buttons */
QPushButton#Pill {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 15px;
    padding: 6px 16px;
    color: {TEXT_DIM};
    font-size: 12px;
}}
QPushButton#Pill:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; border-color: {BORDER_STRONG}; }}
QPushButton#Pill:checked {{
    background: rgba(108,140,255,0.18); border: 1px solid {ACCENT}; color: {ACCENT_HI};
}}

/* ---------------------------------------------------------- primary buttons */
QPushButton#Primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT}, stop:1 #5A78F0);
    border: none; border-radius: 10px; padding: 11px 26px;
    color: white; font-size: 13px; font-weight: 600;
}}
QPushButton#Primary:hover  {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT_HI}, stop:1 {ACCENT}); }}
QPushButton#Primary:pressed {{ background: {ACCENT_DIM}; }}
QPushButton#Primary:disabled {{ background: rgba(255,255,255,0.07); color: {TEXT_FAINT}; }}

QPushButton#Ghost {{
    background: transparent; border: 1px solid {BORDER_STRONG};
    border-radius: 10px; padding: 11px 22px; color: {TEXT_DIM}; font-size: 13px;
}}
QPushButton#Ghost:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; border-color: {ACCENT}; }}

QPushButton#Danger {{
    background: rgba(255,92,108,0.14);
    border: 1px solid rgba(255,92,108,0.55);
    border-radius: 10px; padding: 11px 26px;
    color: #FF8C99; font-size: 13px; font-weight: 600;
}}
QPushButton#Danger:hover {{ background: rgba(255,92,108,0.26); color: white; border-color: {DANGER}; }}

/* ---------------------------------------------------------- list */
QListWidget#AppList {{
    background: transparent; border: none; padding: 4px 2px;
}}
QListWidget#AppList::item {{
    background: {SURFACE};
    border: 1px solid transparent;
    border-radius: {RADIUS}px;
    margin: 4px 2px;
    padding: 0px;
    color: {TEXT};
}}
QListWidget#AppList::item:hover {{
    background: {SURFACE_HOVER};
    border: 1px solid {BORDER};
}}
QListWidget#AppList::item:selected {{
    background: {SURFACE_ACTIVE};
    border: 1px solid rgba(108,140,255,0.65);
}}

/* ---------------------------------------------------------- scrollbar */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.13); border-radius: 5px; min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.26); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

/* ---------------------------------------------------------- text / log */
QPlainTextEdit#Log {{
    background: rgba(6,8,12,0.55);
    border: 1px solid rgba(255,255,255,0.055);
    border-radius: {RADIUS}px;
    color: #A9B2C6;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11.5px;
    padding: 10px 12px;
    selection-background-color: {ACCENT_DIM};
}}
QPlainTextEdit#Log QScrollBar:vertical {{ background: transparent; }}

/* ---------------------------------------------------------- progress */
QProgressBar {{
    background: rgba(255,255,255,0.07);
    border: none; border-radius: 3px; height: 6px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 3px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {SUCCESS});
}}

/* ---------------------------------------------------------- checkbox */
QCheckBox {{
    color: {TEXT_DIM}; font-size: 12px; spacing: 7px;
}}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.28);
    background: rgba(255,255,255,0.05);
}}
QCheckBox::indicator:hover {{
    border: 1px solid {ACCENT};
    background: rgba(108,140,255,0.14);
}}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT}, stop:1 #4F6BE0);
    border: 1px solid {ACCENT};
}}

/* ---------------------------------------------------------- tooltip */
QToolTip {{
    background: #1A1E28; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 8px; padding: 6px 10px; font-size: 12px;
}}
"""

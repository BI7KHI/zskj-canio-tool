"""现代化深色工业风主题（QSS + 调色板）。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

# --------------------------------------------------------------------------- #
# 调色板
# --------------------------------------------------------------------------- #
BG_ROOT = "#0A0E13"
BG_PANEL = "#111823"
BG_CARD = "#151D29"
BG_CARD_HI = "#1A2432"
BG_INPUT = "#0D131B"
BG_HOVER = "#1E2939"

BORDER = "#22303F"
BORDER_HI = "#2E3F52"

TEXT = "#E6EDF5"
TEXT_DIM = "#94A6BC"
TEXT_MUTE = "#65788F"

ACCENT = "#22D3EE"          # 主强调色（青）
ACCENT_DK = "#0E7490"
ACCENT_GLOW = "#0B3A45"

OK = "#25D07A"              # 通 / 闭合
OK_DK = "#0F7A47"
WARN = "#F5A524"
ERR = "#F04A5A"
RX = "#38BDF8"
TX = "#A78BFA"
IDLE = "#31404F"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"


def mono_font(size: int = 10, bold: bool = False) -> QFont:
    f = QFont(FONT_MONO, size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setBold(bold)
    return f


def ui_font(size: int = 10, bold: bool = False) -> QFont:
    f = QFont(FONT_UI, size)
    f.setBold(bold)
    return f


def c(hexstr: str, alpha: int = 255) -> QColor:
    col = QColor(hexstr)
    col.setAlpha(alpha)
    return col


# --------------------------------------------------------------------------- #
# 全局样式表
# --------------------------------------------------------------------------- #
QSS = f"""
* {{
    font-family: "{FONT_UI}";
    font-size: 12px;
    outline: none;
}}

QWidget {{
    background: {BG_ROOT};
    color: {TEXT};
}}

QToolTip {{
    background: {BG_CARD_HI};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------------- 卡片 / 分组 ---------------- */
QFrame#Card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#CardFlat {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#CardTitle {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
    padding: 0px;
    background: transparent;
}}
QLabel#CardHint, QLabel#Hint {{
    color: {TEXT_MUTE};
    font-size: 11px;
    background: transparent;
}}
QLabel#SectionLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#Value {{
    color: {TEXT};
    background: transparent;
}}
QLabel#Mono {{
    font-family: "{FONT_MONO}";
    background: transparent;
}}
QLabel#Title {{
    font-size: 17px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
QLabel#SubTitle {{
    font-size: 11px;
    color: {TEXT_MUTE};
    background: transparent;
}}

/* ---------------- 按钮 ---------------- */
QPushButton {{
    background: {BG_CARD_HI};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 7px;
    padding: 6px 14px;
    min-height: 20px;
}}
QPushButton:hover   {{ background: {BG_HOVER}; border-color: {ACCENT_DK}; }}
QPushButton:pressed {{ background: {BG_INPUT}; }}
QPushButton:disabled {{
    background: {BG_PANEL}; color: {TEXT_MUTE}; border-color: {BORDER};
}}

QPushButton#Primary {{
    background: {ACCENT_DK};
    border: 1px solid {ACCENT};
    color: #EAFBFF;
    font-weight: 600;
}}
QPushButton#Primary:hover   {{ background: {ACCENT}; color: #04222A; }}
QPushButton#Primary:disabled {{ background: {BG_PANEL}; color: {TEXT_MUTE}; border-color: {BORDER}; }}

QPushButton#Danger {{
    background: #4A1620; border: 1px solid {ERR}; color: #FFE3E7; font-weight: 600;
}}
QPushButton#Danger:hover {{ background: {ERR}; color: #2A0509; }}

QPushButton#Ghost {{
    background: transparent; border: 1px solid {BORDER}; color: {TEXT_DIM};
    padding: 4px 10px;
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {ACCENT_DK}; }}

QPushButton#Mini {{
    padding: 3px 9px; min-height: 16px; font-size: 11px;
    background: {BG_CARD_HI}; border: 1px solid {BORDER}; border-radius: 6px;
}}
QPushButton#Mini:hover {{ border-color: {ACCENT_DK}; color: {ACCENT}; }}

/* ---------------- 输入控件 ---------------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_HI};
    border-radius: 7px;
    padding: 5px 9px;
    color: {TEXT};
    selection-background-color: {ACCENT_DK};
    min-height: 18px;
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {ACCENT_DK}; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{
    color: {TEXT_MUTE}; background: {BG_PANEL}; border-color: {BORDER};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER_HI};
    border-radius: 6px;
    selection-background-color: {ACCENT_DK};
    selection-color: #EAFBFF;
    padding: 3px;
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG_CARD_HI}; border: none; width: 16px;
}}
QSpinBox::up-arrow {{
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid {TEXT_DIM};
}}
QSpinBox::down-arrow {{
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
}}

QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER_HI};
    background: {BG_INPUT};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
    image: none;
}}
QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {TEXT_MUTE}; }}

/* ---------------- 标签页 ---------------- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {BG_PANEL};
    top: -1px;
}}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 18px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; background: {BG_CARD}; }}
QTabBar::tab:selected {{
    color: {ACCENT};
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-bottom-color: {BG_PANEL};
}}

/* ---------------- 表格 ---------------- */
QTableWidget, QTableView {{
    background: {BG_INPUT};
    alternate-background-color: #101722;
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: #1B2634;
    selection-background-color: {ACCENT_DK};
    selection-color: #EAFBFF;
    font-family: "{FONT_MONO}";
    font-size: 12px;
}}
QTableWidget::item, QTableView::item {{ padding: 3px 6px; border: none; }}
QTableWidget::item:selected {{ background: {ACCENT_DK}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_DIM};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-family: "{FONT_UI}";
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::section:hover {{ color: {TEXT}; }}
QTableCornerButton::section {{ background: {BG_CARD}; border: none; }}

/* ---------------- 列表 / 文本域 ---------------- */
QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    font-family: "{FONT_MONO}";
    font-size: 12px;
    selection-background-color: {ACCENT_DK};
}}
QListWidget {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 3px;
}}
QListWidget::item {{ padding: 5px 7px; border-radius: 5px; }}
QListWidget::item:selected {{ background: {ACCENT_DK}; color: #EAFBFF; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}

/* ---------------- 滚动条 ---------------- */
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2B3A4D; border-radius: 5px; min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DK}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: #2B3A4D; border-radius: 5px; min-width: 26px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DK}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------------- 其它 ---------------- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 9px;
    margin-top: 9px;
    padding-top: 9px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 11px;
    padding: 0 5px;
    color: {TEXT_DIM};
}}
QStatusBar {{
    background: {BG_PANEL};
    border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
}}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:hover {{ background: {ACCENT_DK}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QMenu {{
    background: {BG_CARD}; border: 1px solid {BORDER_HI};
    border-radius: 7px; padding: 4px;
}}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_DK}; color: #EAFBFF; }}
QProgressBar {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 6px; text-align: center; color: {TEXT_DIM};
}}
QProgressBar::chunk {{ background: {ACCENT_DK}; border-radius: 5px; }}
"""


def apply_theme(app) -> None:
    """给 QApplication 套用深色主题。"""
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    pal = app.palette()
    pal.setColor(pal.ColorRole.Window, c(BG_ROOT))
    pal.setColor(pal.ColorRole.WindowText, c(TEXT))
    pal.setColor(pal.ColorRole.Base, c(BG_INPUT))
    pal.setColor(pal.ColorRole.AlternateBase, c(BG_PANEL))
    pal.setColor(pal.ColorRole.Text, c(TEXT))
    pal.setColor(pal.ColorRole.Button, c(BG_CARD_HI))
    pal.setColor(pal.ColorRole.ButtonText, c(TEXT))
    pal.setColor(pal.ColorRole.Highlight, c(ACCENT_DK))
    pal.setColor(pal.ColorRole.HighlightedText, c("#EAFBFF"))
    pal.setColor(pal.ColorRole.ToolTipBase, c(BG_CARD_HI))
    pal.setColor(pal.ColorRole.ToolTipText, c(TEXT))
    app.setPalette(pal)

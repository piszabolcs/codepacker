# -*- coding: utf-8 -*-
#
# this is the dark theme, it's one big QSS string
# QSS is almost the same as CSS, just for Qt

# colors in one place so they're easy to change
COLORS = {
    "background": "#12141c",
    "background_light": "#1a1d28",
    "log_background": "#0d0f16",
    "panel": "#1e2230",
    "panel_hover": "#262b3b",
    "border": "#2e3446",
    "text": "#e4e7f0",
    "text_muted": "#8b93a8",
    "accent": "#4c7dff",
    "accent_hover": "#5f8cff",
    "accent_dark": "#3563d9",
    # white text on the primary button: 5.3:1 (WCAG AA wants 4.5:1 for 14 px text)
    "primary": "#3563d9",
    "primary_hover": "#2e5ac8",
    "primary_pressed": "#2b54c0",
    # the frame of an unchecked check box: at least 3:1 against every background it sits on
    "control_border": "#6b7590",
    "green": "#3ecf8e",
    "yellow": "#f5b455",
    "red": "#f2555a",
}


def stylesheet():
    # assemble the full stylesheet from the colors
    return """
    QWidget {{
        background-color: {background};
        color: {text};
        font-family: "Segoe UI", "Inter", Arial, sans-serif;
        font-size: 13px;
    }}

    QMainWindow {{
        background-color: {background};
    }}

    /* labels shouldn't have their own background, otherwise they'd look like boxes
       on the lighter panel */
    QLabel {{
        background-color: transparent;
    }}

    QCheckBox {{
        background-color: transparent;
    }}

    /* keyboard focus is always visible, in the accent colour */
    QPushButton:focus, QToolButton:focus {{
        border: 1px solid {accent};
    }}

    QCheckBox:focus {{
        border: 1px solid {accent};
    }}

    QTreeView:focus, QPlainTextEdit:focus {{
        border: 1px solid {accent};
    }}

    /* the settings header that folds the settings in and out */
    QToolButton#toggle {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        color: {text};
        font-weight: 600;
        padding: 4px 6px;
    }}

    QToolButton#toggle:hover {{
        background-color: {panel_hover};
    }}

    /* the author signature: bare text, no border or box, the glow comes from code */
    QPushButton#signature, QPushButton#signature:hover, QPushButton#signature:focus {{
        background-color: transparent;
        border: none;
        color: {text_muted};
        font-size: 11px;
        padding: 2px 10px;
    }}

    QPushButton#signature:hover, QPushButton#signature:focus {{
        color: {text};
    }}

    /* the close cross of the About card */
    QPushButton#close {{
        background-color: transparent;
        border: 1px solid transparent;
        font-size: 16px;
        padding: 0px 8px;
    }}

    QPushButton#close:hover, QPushButton#close:focus {{
        border: 1px solid {accent};
    }}

    /* the app's name in the top bar and the About card */
    QLabel#title {{
        font-size: 19px;
        font-weight: 600;
        color: {text};
    }}

    QLabel#section {{
        font-size: 11px;
        font-weight: 600;
        color: {text_muted};
        text-transform: uppercase;
    }}

    QLabel#muted {{
        color: {text_muted};
        font-size: 12px;
    }}

    QLabel#summary {{
        font-weight: 600;
    }}

    /* panels are set apart with a thin border and rounded corners */
    QDialog#about {{ background: transparent; border: none; }}
    QFrame#card {{
        background-color: {panel};
        border: 1px solid {border};
        border-radius: 10px;
    }}

    /* text input fields */
    QLineEdit, QSpinBox, QComboBox {{
        background-color: {background_light};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 5px 8px;
        color: {text};
        selection-background-color: {accent};
    }}

    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {accent};
    }}

    QLineEdit:disabled, QSpinBox:disabled {{
        color: {text_muted};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {panel};
        border: 1px solid {border};
        selection-background-color: {accent};
        outline: none;
    }}

    /* buttons */
    QPushButton {{
        background-color: {panel_hover};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 8px 16px;
        color: {text};
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {border};
        border: 1px solid {accent};
    }}

    QPushButton:pressed {{
        background-color: {background_light};
    }}

    QPushButton:disabled {{
        color: {text_muted};
        background-color: {background_light};
        border: 1px solid {border};
    }}

    /* the main button that builds the package */
    QPushButton#primary {{
        background-color: {primary};
        border: 1px solid {primary};
        color: #ffffff;
        font-weight: 600;
        font-size: 14px;
        padding: 7px 22px;
        border-radius: 8px;
    }}

    QPushButton#primary:hover {{
        background-color: {primary_hover};
    }}

    QPushButton#primary:focus {{
        border: 1px solid #ffffff;
    }}

    QPushButton#primary:pressed {{
        background-color: {primary_pressed};
    }}

    QPushButton#primary:disabled {{
        background-color: {border};
        border: 1px solid {border};
        color: {text_muted};
    }}

    /* the small flat buttons above the list */
    QPushButton#flat {{
        background-color: transparent;
        border: 1px solid {border};
        padding: 5px 11px;
        font-size: 12px;
    }}

    QPushButton#flat:hover, QPushButton#flat:focus {{
        background-color: {panel_hover};
        border: 1px solid {accent};
    }}

    /* checkbox; the transparent border keeps it still when the focus frame appears */
    QCheckBox {{
        spacing: 8px;
        padding: 3px;
        border: 1px solid transparent;
        border-radius: 4px;
    }}

    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 4px;
        border: 1px solid {control_border};
        background-color: {background_light};
    }}

    QCheckBox::indicator:hover {{
        border: 1px solid {accent};
    }}

    QCheckBox::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
        image: none;
    }}

    /* the tree list */
    QTreeView {{
        background-color: {background_light};
        border: 1px solid {border};
        border-radius: 8px;
        outline: none;
        alternate-background-color: {panel};
    }}

    QTreeView::item {{
        padding: 2px 2px;
        border: none;
    }}

    QTreeView::item:hover {{
        background-color: {panel_hover};
    }}

    QTreeView::item:selected {{
        background-color: {accent_dark};
        color: #ffffff;
    }}

    QTreeView::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {control_border};
        background-color: {background};
    }}

    QTreeView::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
    }}

    QTreeView::indicator:indeterminate {{
        background-color: {text_muted};
        border: 1px solid {text_muted};
    }}

    QHeaderView::section {{
        background-color: {panel};
        color: {text_muted};
        border: none;
        border-bottom: 1px solid {border};
        padding: 7px 6px;
        font-weight: 600;
        font-size: 12px;
    }}

    /* the log window */
    QPlainTextEdit {{
        background-color: {log_background};
        border: 1px solid {border};
        border-radius: 8px;
        color: #b9c0d4;
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: 12px;
        padding: 6px;
    }}

    /* progress bar */
    QProgressBar {{
        background-color: {background_light};
        border: 1px solid {border};
        border-radius: 6px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}

    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 5px;
    }}

    /* scrollbar */
    /* inset from the rounded corners of the lists and the log */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 10px;
        margin: 10px 0px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {border};
        border-radius: 5px;
        min-height: 28px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {text_muted};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 10px;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {border};
        border-radius: 5px;
        min-width: 28px;
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* tabs */
    QTabWidget::pane {{
        border: 1px solid {border};
        border-radius: 8px;
        background-color: {background_light};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {text_muted};
        padding: 7px 12px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
    }}

    QTabBar::tab:selected {{
        color: {text};
        border-bottom: 2px solid {accent};
    }}

    QTabBar::tab:hover {{
        color: {text};
    }}

    /* bottom status bar */
    QStatusBar {{
        background-color: {background_light};
        border-top: 1px solid {border};
        color: {text_muted};
    }}

    QStatusBar::item {{
        border: none;
    }}

    /* menu */
    QMenuBar {{
        background-color: {background_light};
        border-bottom: 1px solid {border};
    }}

    QMenuBar::item {{
        padding: 6px 12px;
        background-color: transparent;
    }}

    QMenuBar::item:selected {{
        background-color: {panel_hover};
    }}

    QMenu {{
        background-color: {panel};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 7px 24px 7px 14px;
        border-radius: 4px;
    }}

    QMenu::item:selected {{
        background-color: {accent};
        color: #ffffff;
    }}

    /* splitter handle */
    QSplitter::handle {{
        background-color: {border};
    }}

    QSplitter::handle:horizontal {{
        width: 3px;
    }}

    QToolTip {{
        background-color: {panel};
        color: {text};
        border: 1px solid {accent};
        border-radius: 4px;
        padding: 5px;
    }}
    """.format(**COLORS)

# -*- coding: utf-8 -*-
#
# the author signature: a small footer button "psz // v<version>" with an accent glow on hover
# and keyboard focus, and the compact About card it opens (closes on X, Esc and a click
# outside); the version comes from codepacker.__version__ and is printed nowhere else

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from .. import APP_NAME, __version__
from . import theme

GLOW_RADIUS = 18
GLOW_MILLISECONDS = 180

PURPOSE = ("Bundle a source folder into one upload-ready Markdown file for AI chats "
           "— without secrets.")
LAYERS = ("core (scan · filter · secret scan · bundle, Qt-free) → "
          "workers (QThread) → ui (PySide6)")
BUILT_WITH = "Python 3.12 · PySide6 · PyInstaller"
REPOSITORIES = (
    "https://github.com/piszabolcs/CodePacker",
    "PySide6 — code.qt.io/pyside/pyside-setup",
    "PyInstaller — github.com/pyinstaller/pyinstaller",
)


def signature_text():
    return "psz // v{}".format(__version__)


def animations_enabled():
    # the system's "show animations" setting: without it the glow simply switches on and off
    return QApplication.isEffectEnabled(Qt.UIEffect.UI_General)


class SignatureButton(QPushButton):
    # bare footer text, no border or box; only a glow in the theme accent shows it is a button

    def __init__(self, parent=None):
        super().__init__(signature_text(), parent)
        self.setObjectName("signature")
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("About " + APP_NAME)
        self.setAccessibleName("About " + APP_NAME)

        self.glow = QGraphicsDropShadowEffect(self)
        self.glow.setColor(QColor(theme.COLORS["accent"]))
        self.glow.setOffset(0, 0)
        self.glow.setBlurRadius(0)
        self.setGraphicsEffect(self.glow)

        self.glow_animation = QPropertyAnimation(self.glow, b"blurRadius", self)
        self.glow_animation.setDuration(GLOW_MILLISECONDS)
        self.glow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_glow(self, on):
        target = GLOW_RADIUS if on else 0
        self.glow_animation.stop()
        if not animations_enabled():
            self.glow.setBlurRadius(target)
            return
        self.glow_animation.setStartValue(self.glow.blurRadius())
        self.glow_animation.setEndValue(target)
        self.glow_animation.start()

    def enterEvent(self, event):
        self.set_glow(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        # a button that still has the keyboard focus keeps its glow (spec C-22)
        if not self.hasFocus():
            self.set_glow(False)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.set_glow(True)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        if not self.underMouse():
            self.set_glow(False)
        super().focusOutEvent(event)


class AboutDialog(QDialog):
    # a compact release card, centered over the window; a popup, so a click outside closes it

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("about")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("About " + APP_NAME)
        self.setFixedWidth(430)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)  # room for the rounded shadow
        card = QFrame()
        card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 170))
        card.setGraphicsEffect(shadow)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 14, 18)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.title_label = QLabel("{} v{}".format(APP_NAME, __version__))
        self.title_label.setObjectName("title")
        top.addWidget(self.title_label)
        top.addStretch(1)
        close_button = QPushButton("×")
        close_button.setObjectName("close")
        close_button.setToolTip("Close")
        close_button.setAccessibleName("Close")
        close_button.clicked.connect(self.reject)
        top.addWidget(close_button)
        layout.addLayout(top)

        purpose = QLabel(PURPOSE)
        purpose.setWordWrap(True)
        layout.addWidget(purpose)
        self.add_section(layout, "Architecture", LAYERS)
        self.add_section(layout, "Built with", BUILT_WITH)
        self.add_section(layout, "Repositories", "\n".join(REPOSITORIES))
        outer.addWidget(card)

    def add_section(self, layout, heading, body):
        heading_label = QLabel(heading)
        heading_label.setObjectName("section")
        layout.addWidget(heading_label)
        body_label = QLabel(body)
        body_label.setObjectName("muted")
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body_label)

    def showEvent(self, event):
        # centered over the window that opened it
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            center = parent.mapToGlobal(parent.rect().center())
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        super().showEvent(event)

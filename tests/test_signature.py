"""The author signature (Global Constraint 9): footer label, glow, About card."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QFocusEvent

from codepacker import __version__
from codepacker.ui import signature
from codepacker.ui.main_window import MainWindow


def test_the_footer_shows_the_signature_and_opens_the_about_card(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    button = window.signature_button
    assert button.text() == f"psz // v{__version__}"
    assert button in window.statusBar().findChildren(signature.SignatureButton)
    assert button.isFlat() and button.cursor().shape() == Qt.CursorShape.PointingHandCursor

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    dialog = window.about_dialog
    assert dialog.isVisible()
    assert dialog.title_label.text() == f"CodePacker v{__version__}"
    texts = " ".join(label.text() for label in dialog.findChildren(type(dialog.title_label)))
    for part in (signature.PURPOSE, signature.LAYERS, signature.BUILT_WITH,
                 "https://github.com/piszabolcs/CodePacker"):
        assert part in texts
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()


def test_the_glow_follows_hover_and_focus_and_stays_while_focused(qtbot, monkeypatch):
    monkeypatch.setattr(signature, "animations_enabled", lambda: False)  # no waiting
    button = signature.SignatureButton()
    qtbot.addWidget(button)
    point = QPointF(2, 2)

    button.enterEvent(QEnterEvent(point, point, point))
    assert button.glow.blurRadius() == signature.GLOW_RADIUS
    button.leaveEvent(QEvent(QEvent.Type.Leave))
    assert button.glow.blurRadius() == 0

    button.focusInEvent(QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason))
    assert button.glow.blurRadius() == signature.GLOW_RADIUS
    monkeypatch.setattr(button, "hasFocus", lambda: True)
    button.leaveEvent(QEvent(QEvent.Type.Leave))  # spec C-22: focus keeps the glow
    assert button.glow.blurRadius() == signature.GLOW_RADIUS


def test_the_glow_animates_in_the_accent_colour(qtbot, monkeypatch):
    monkeypatch.setattr(signature, "animations_enabled", lambda: True)
    button = signature.SignatureButton()
    qtbot.addWidget(button)
    point = QPointF(2, 2)
    button.enterEvent(QEnterEvent(point, point, point))
    assert 150 <= button.glow_animation.duration() <= 200
    assert button.glow.color().name() == signature.theme.COLORS["accent"]
    qtbot.waitUntil(lambda: button.glow.blurRadius() == signature.GLOW_RADIUS, timeout=2_000)

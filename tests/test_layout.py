"""Layout and accessibility (spec G-1...G-5, 5.4, 5.5): fits, no overlaps, focus, contrast."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QAbstractButton

from codepacker import core
from codepacker.ui import theme
from codepacker.ui.main_window import MainWindow
from gui_helpers import measure_layout, tree_rows

REPO_ROOT = Path(__file__).resolve().parent.parent

# The same measurement in a fresh interpreter, with Qt scaling everything by 1.5.
SCALED_MEASUREMENT = """
import json, os, sys, tempfile
sys.path[:0] = ["tests", "."]
os.environ["APPDATA"] = tempfile.mkdtemp()
from PySide6.QtWidgets import QApplication
from codepacker import settings
settings.settings_file_override = os.path.join(tempfile.mkdtemp(), "settings.ini")
from codepacker.ui.main_window import MainWindow
from gui_helpers import measure_layout
app = QApplication([])
window = MainWindow()
print(json.dumps(measure_layout(window)))
window.close()
"""


def _check(report):
    for state, (width, height) in report["minimum"].items():
        assert width <= 1020 and height <= 680, state
    for state, width, height, rows, overlaps, clipped in report["sizes"]:
        assert (overlaps, clipped) == ([], []), (state, width, height)
        if (width, height) == (1020, 680):
            assert rows >= 8, state
        if (width, height) == (1366, 728):
            assert rows >= 12, state


def test_the_layout_fits_and_nothing_overlaps_or_is_clipped(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    _check(measure_layout(window))


def test_the_layout_also_fits_at_a_scale_factor_of_1_5():
    environment = {**os.environ, "QT_SCALE_FACTOR": "1.5", "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run([sys.executable, "-c", SCALED_MEASUREMENT], cwd=REPO_ROOT,
                            env=environment, capture_output=True, text=True, timeout=120,
                            check=False)
    assert result.returncode == 0, result.stderr
    _check(json.loads(result.stdout.strip().splitlines()[-1]))


def _contrast(first, second):
    def luminance(colour):
        channels = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted([luminance(first), luminance(second)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_theme_meets_the_contrast_minimums_and_shows_the_focus():
    colours = theme.COLORS
    for background in (colours["primary"], colours["primary_hover"],
                       colours["primary_pressed"]):
        assert _contrast("#ffffff", background) >= 4.5
    for background in (colours["background"], colours["background_light"], colours["panel"]):
        assert _contrast(colours["control_border"], background) >= 3.0
    sheet = theme.stylesheet()
    assert "QPushButton#primary {{\n        background-color: {}".format(
        colours["primary"]).replace("{{", "{") in sheet
    for selector in ("QPushButton:focus", "QCheckBox:focus", "QPushButton#flat:focus",
                     "QTreeView:focus", "QToolButton:focus"):
        assert re.search(re.escape(selector) + r"[^{]*\{[^}]*border: 1px solid "
                         + colours["accent"], sheet), selector


def test_keys_tooltips_and_plurals(qtbot, message_boxes):
    window = MainWindow()
    qtbot.addWidget(window)
    buttons = [button for button in window.findChildren(QAbstractButton)
               if button.isVisibleTo(window) or button.parent() is window.settings_body]
    assert [button.text() for button in buttons if not button.toolTip()] == []

    # Enter in the folder field scans, Ctrl+B builds (both refuse: nothing is chosen yet)
    window.project_edit.returnPressed.emit()
    assert window.build_action.shortcut().toString() == "Ctrl+B"
    window.build_action.trigger()
    assert [text for _, (_, text) in message_boxes] == [
        "Please choose an existing project folder first.", "Please scan a project folder first."]

    window.entries = [core.FileEntry("C:/demo/" + path, path, 6)
                      for path in ("one/a.py", "two/b.py", "two/c.py")]
    window.fill_tree()
    model = window.tree.model()
    folders = [model.index(row, 0).data() for row in range(model.rowCount())]
    assert folders == ["one   (1 file)", "two   (2 files)"]
    assert window.summary_label.text().startswith("3 of 3 files selected")
    assert len(tree_rows(window)) == 5

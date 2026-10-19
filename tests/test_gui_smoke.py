"""GUI smoke tests: the main window works offscreen (pytest-qt; never shown on screen)."""

import os
import re

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTreeWidget,
)

from codepacker.ui import theme
from codepacker.ui.main_window import MainWindow, asset_path
from codepacker.ui.signature import AboutDialog
from fixtures import PRIVATE_KEY_CONTENT_FILES, SECRET_NAME_FILES, hostile_tree, only
from gui_helpers import listed_paths


@pytest.fixture
def window(qtbot):
    main_window = MainWindow()
    qtbot.addWidget(main_window)  # closed and deleted by pytest-qt after the test
    return main_window


def _button(window, text):
    buttons = [b for b in window.findChildren(QPushButton) if b.text() == text]
    return only(buttons, f"button {text!r}")


def test_main_py_starts_the_gui_through_codepacker_ui_app_run():
    import main  # the repository root is on sys.path (pytest.ini); importing starts nothing

    from codepacker.ui import app

    assert main.run is app.run


def test_main_window_constructs_offscreen(window):
    assert QGuiApplication.platformName() == "offscreen"
    assert window.centralWidget() is not None
    assert not window.isVisible()


def test_main_window_has_the_expected_widgets(window):
    assert [action.text() for action in window.menuBar().actions()] == ["File", "Help"]
    labels = {label.text() for label in window.findChildren(QLabel)}
    assert {"Files", "Max part size", "Output folder"} <= labels
    assert window.settings_toggle.text() == "Settings"
    buttons = {button.text() for button in window.findChildren(QPushButton)}
    assert {"Browse folder…", "Browse…", "Scan", "Select all", "Select none",
            "Clear log", "Build package", "Cancel", "Open output folder", "Copy path"} <= buttons
    tabs = only(window.findChildren(QTabWidget), "tab widget")
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Log", "Statistics", "Excluded"]
    headers = sorted(
        tuple(tree.headerItem().text(column) for column in range(tree.columnCount()))
        for tree in window.findChildren(QTreeWidget)
    )
    assert headers == [("Path", "Reason", "Rule"), ("Type", "Count", "Size")]
    model = window.tree.model()
    assert [model.headerData(column, Qt.Orientation.Horizontal)
            for column in range(model.columnCount())] == ["File", "Size"]
    log = only(window.findChildren(QPlainTextEdit), "log view")
    assert log.isReadOnly()
    assert window.findChild(QProgressBar) is not None


def test_the_icons_are_found_when_running_from_source(window):
    assert os.path.isfile(asset_path(os.path.join("assets", "icon.ico")))
    assert os.path.isfile(asset_path(os.path.join("assets", "icon_256.png")))
    assert not window.windowIcon().isNull()


def test_every_object_name_used_by_the_ui_has_a_theme_rule(window):
    """The theme styles widgets through "#objectName" selectors: a name without a rule (for
    example after renaming it on one side only) would silently drop the widget's style."""
    styled = set(re.findall(r"#(\w+)", theme.stylesheet()))
    named = {
        widget.objectName()
        for parent in (window, AboutDialog(window))
        for widget in parent.findChildren(QFrame) + parent.findChildren(QPushButton)
        if widget.objectName() and not widget.objectName().startswith("qt_")
    }
    assert named  # the check below must not pass vacuously
    assert named <= styled


SMALL_PROJECT = {
    "main.py": "print('hello')\n",
    "src/app.js": "console.log('hello');\n",
    "README.md": "# Small project\n",
    "node_modules/x/index.js": "module.exports = 1;\n",
    ".env": "SECRET=fake\n",
}


def _drop_and_scan(window, qtbot, folder):
    """Drop ``folder`` on the window (the GUI entry point: fills it in and scans) and wait."""
    scan_button = _button(window, "Scan")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder))])
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    assert not scan_button.isEnabled()  # the scan runs in a worker thread
    qtbot.waitUntil(scan_button.isEnabled, timeout=10_000)


def test_dropping_a_small_project_scans_it_without_errors(
    window, qtbot, make_project, tmp_path, message_boxes
):
    root = make_project(tmp_path / "small_project", SMALL_PROJECT)
    _drop_and_scan(window, qtbot, root)

    assert message_boxes == []
    assert listed_paths(window) == ["README.md", "main.py", "src/app.js"]


def test_secret_files_are_never_offered_for_selection(window, qtbot, tmp_path, message_boxes):
    """Hard exclusion (spec S-1, S-2): no tree row, so "Select all" cannot pick them either;
    the window keeps them as secret exclusions for the tree to show as locked."""
    root = hostile_tree(tmp_path / "project", junctions=False)
    _drop_and_scan(window, qtbot, root)
    _button(window, "Select all").click()

    secret_paths = {*SECRET_NAME_FILES, *PRIVATE_KEY_CONTENT_FILES}
    listed = listed_paths(window)
    assert listed  # the checks below must not pass vacuously
    assert sorted(secret_paths.intersection(listed)) == []
    selected = {entry.relative_path for entry in window.selected_entries()}
    assert selected == set(listed)
    locked = {exclusion.rel_path for exclusion in window.exclusions if exclusion.kind == "secret"}
    assert locked == secret_paths


def test_building_without_an_output_folder_writes_next_to_the_project(
    window, qtbot, make_project, tmp_path, message_boxes
):
    root = make_project(tmp_path / "small_project", SMALL_PROJECT)
    _drop_and_scan(window, qtbot, root)

    _button(window, "Build package").click()  # MD only (the default), output folder left empty
    qtbot.waitUntil(lambda: len(message_boxes) > 0, timeout=10_000)

    output = tmp_path / "small_project_codepacker"
    assert [kind for kind, _ in message_boxes] == ["information"]
    assert sorted(path.name for path in output.iterdir()) == ["small_project_combined.md"]
    bundle = (output / "small_project_combined.md").read_text(encoding="utf-8")
    assert "\n## FILE: main.py\n" in bundle


def test_the_log_fades_only_towards_hidden_lines(window):
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    for line in range(200):
        window.log_message(f"line {line}")
    bar = window.log_view.verticalScrollBar()
    QGuiApplication.processEvents()
    assert bar.maximum() > 0  # the log must really scroll, or the checks pass vacuously

    bar.setValue(bar.minimum())
    assert (window.log_fade.top.isVisible(), window.log_fade.bottom.isVisible()) == (False, True)
    bar.setValue(bar.maximum() // 2)
    assert (window.log_fade.top.isVisible(), window.log_fade.bottom.isVisible()) == (True, True)
    bar.setValue(bar.maximum())
    assert (window.log_fade.top.isVisible(), window.log_fade.bottom.isVisible()) == (True, False)

"""Helpers for the GUI tests (a helper module, not a test module)."""

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

from codepacker import core
from codepacker.ui.file_tree import PATH_ROLE

LAYOUT_SIZES = [(1020, 680), (1280, 820), (1920, 1080)]


def tree_rows(window):
    """[(relative path or None for a folder, check state)] of every row of the file tree."""
    model = window.tree.model()
    rows = []

    def walk(parent):
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            state = Qt.CheckState(index.data(Qt.ItemDataRole.CheckStateRole))
            rows.append((index.data(PATH_ROLE), state))
            walk(index)

    walk(QModelIndex())
    return rows


def listed_paths(window):
    """The relative path of every file row in the tree, sorted."""
    return sorted(path for path, _ in tree_rows(window) if path is not None)


def checked_paths(window):
    return sorted(path for path, state in tree_rows(window)
                  if path is not None and state == Qt.CheckState.Checked)


def _name(widget):
    return "{}({!r})".format(type(widget).__name__, getattr(widget, "text", lambda: "")())


def layout_problems(window):
    """(overlaps, clipped) among the shown widgets: siblings whose rectangles intersect, and
    labels or buttons smaller than they need to show their text."""
    overlaps = []
    clipped = []
    widgets = [window, *window.findChildren(QWidget)]
    for parent in widgets:
        if not parent.isVisible():
            continue
        children = [child for child in parent.children()
                    if isinstance(child, QWidget) and child.isVisible() and not child.isWindow()
                    and not child.objectName().startswith("qt_")]
        for position, first in enumerate(children):
            for second in children[position + 1:]:
                if first.geometry().intersects(second.geometry()):
                    overlaps.append((_name(first), _name(second)))
    for widget in widgets:
        if not isinstance(widget, (QLabel, QAbstractButton)) or not widget.isVisible():
            continue
        needed = widget.minimumSizeHint()
        if isinstance(widget, QLabel) and widget.wordWrap():
            needed.setHeight(widget.heightForWidth(widget.width()))
        if widget.width() < needed.width() or widget.height() < needed.height():
            clipped.append(_name(widget))
    return overlaps, clipped


def visible_tree_rows(window):
    """How many whole rows of the file tree fit into its viewport."""
    model = window.tree.model()
    row_height = window.tree.visualRect(model.index(0, 0)).height()
    return window.tree.viewport().height() // row_height


def fill_demo_tree(window, count=60):
    """Put ``count`` in-memory files (in a few folders) into the window's tree."""
    window.entries = [core.FileEntry(f"C:/demo/src/pkg{index % 3}/module_{index:03d}.py",
                                     f"src/pkg{index % 3}/module_{index:03d}.py", 1200)
                      for index in range(count)]
    window.fill_tree()


def measure_layout(window):
    """{"minimum": [w, h] per settings state, "sizes": [[state, w, h, rows, overlaps, clipped]]}.

    The window is laid out for real but never appears on a screen (offscreen platform, and
    Qt.WA_DontShowOnScreen on top of it).
    """
    from PySide6.QtWidgets import QApplication

    fill_demo_tree(window)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    report = {"minimum": {}, "sizes": []}
    for expanded in (False, True):
        state = "expanded" if expanded else "collapsed"
        window.settings_toggle.setChecked(expanded)
        hint = window.minimumSizeHint()
        report["minimum"][state] = [hint.width(), hint.height()]
        for width, height in [*LAYOUT_SIZES, (1366, 728)]:
            window.resize(width, height)
            QApplication.processEvents()
            overlaps, clipped = layout_problems(window)
            report["sizes"].append([state, width, height, visible_tree_rows(window),
                                    overlaps, clipped])
    return report

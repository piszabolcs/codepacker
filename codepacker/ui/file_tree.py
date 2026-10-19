# -*- coding: utf-8 -*-
#
# the file tree: a Qt model that shows the SelectionModel as folders and files (folders
# first, then files, by name); it only renders, every check mark lives in the SelectionModel
# a check box toggles the files the filter shows, never the hidden ones

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from .. import core

# the relative path of a file row (None for a folder row)
PATH_ROLE = Qt.ItemDataRole.UserRole


class Node:
    __slots__ = ("name", "path", "parent", "row", "children", "files", "size", "is_file")

    def __init__(self, name, path, parent, is_file=False, size=0):
        self.name = name
        self.path = path
        self.parent = parent
        self.row = 0
        self.children = []
        self.files = [path] if is_file else []  # the relative paths of the files at or below
        self.size = size
        self.is_file = is_file


def build_tree(entries):
    # the folder/file tree of the given entries, returns its invisible root node
    root = Node("", "", None)
    folders = {"": root}
    for entry in entries:
        parts = entry.relative_path.split("/")
        parent = root
        for depth in range(1, len(parts)):
            key = "/".join(parts[:depth])
            folder = folders.get(key)
            if folder is None:
                folder = Node(parts[depth - 1], key, parent)
                parent.children.append(folder)
                folders[key] = folder
            parent = folder
        parent.children.append(Node(parts[-1], entry.relative_path, parent, True, entry.size))
    _finish(root)
    return root


def _finish(node):
    node.children.sort(key=lambda child: (child.is_file, child.name.casefold()))
    for row, child in enumerate(node.children):
        child.row = row
        if not child.is_file:
            _finish(child)
        node.files.extend(child.files)
        node.size = node.size + child.size


class FileTreeModel(QAbstractItemModel):

    HEADERS = ("File", "Size")

    def __init__(self, selection, on_change=None, parent=None):
        super().__init__(parent)
        self.selection = selection
        self.on_change = on_change      # called after every change of the check marks
        self.query = ""
        self.root = Node("", "", None)
        self.folder_states = {}         # folder path -> Qt.CheckState, until the next change
        self.rebuild()

    # ------------------------------------------------------------
    # what is shown
    # ------------------------------------------------------------

    def set_selection(self, selection):
        self.selection = selection
        self.rebuild()

    def set_filter(self, query):
        self.query = query
        self.rebuild()

    def rebuild(self):
        self.beginResetModel()
        self.root = build_tree(self.selection.visible(self.query))
        self.folder_states = {}
        self.endResetModel()

    def visible_paths(self):
        return list(self.root.files)

    # ------------------------------------------------------------
    # check marks, always through the SelectionModel
    # ------------------------------------------------------------

    def set_checked(self, relative_paths, checked):
        self.selection.set_checked(relative_paths, checked)
        self.folder_states = {}
        if self.root.children:
            # one signal for the whole tree, the view repaints what it shows
            last = len(self.root.children) - 1
            self.dataChanged.emit(self.index(0, 0), self.index(last, 1),
                                  [Qt.ItemDataRole.CheckStateRole])
        if self.on_change is not None:
            self.on_change()

    def check_state(self, node):
        if node.is_file:
            if self.selection.is_checked(node.path):
                return Qt.CheckState.Checked
            return Qt.CheckState.Unchecked
        state = self.folder_states.get(node.path)
        if state is None:
            checked = sum(1 for path in node.files if self.selection.is_checked(path))
            if checked == len(node.files):
                state = Qt.CheckState.Checked
            elif checked == 0:
                state = Qt.CheckState.Unchecked
            else:
                state = Qt.CheckState.PartiallyChecked
            self.folder_states[node.path] = state
        return state

    # ------------------------------------------------------------
    # QAbstractItemModel
    # ------------------------------------------------------------

    def node(self, index):
        return index.internalPointer() if index.isValid() else self.root

    def index(self, row, column, parent=QModelIndex()):
        children = self.node(parent).children
        if 0 <= row < len(children) and 0 <= column < len(self.HEADERS):
            return self.createIndex(row, column, children[row])
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        parent = index.internalPointer().parent
        if parent is None or parent is self.root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self.node(parent).children)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags = flags | Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 1:
                return core.format_size(node.size)
            if node.is_file:
                return node.name
            return "{}   ({})".format(node.name, core.plural(len(node.files), "file"))
        if role == Qt.ItemDataRole.CheckStateRole and column == 0:
            return self.check_state(node)
        if role == Qt.ItemDataRole.ToolTipRole:
            return node.path
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == PATH_ROLE:
            return node.path if node.is_file else None
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.CheckStateRole or not index.isValid():
            return False
        checked = Qt.CheckState(value) == Qt.CheckState.Checked
        self.set_checked(index.internalPointer().files, checked)
        return True

# -*- coding: utf-8 -*-
#
# this is the main window, the whole interface is assembled here
# the actual work is done by the core package and the background threads in workers.py

import math
import os
import sys
import subprocess

from PySide6.QtCore import Qt, QSize, QTimer, QUrl
from PySide6.QtGui import QIcon, QAction, QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox, QComboBox,
    QTreeView, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QProgressBar,
    QFileDialog, QMessageBox, QSplitter, QFrame, QTabWidget, QToolButton,
    QHeaderView,
)

from .. import APP_NAME, core
from . import theme
from .file_tree import FileTreeModel
from .scroll_fade import attach_scroll_fade
from .selection import SelectionModel
from .signature import AboutDialog, SignatureButton
from ..settings import Settings
from ..workers import ScanWorker, PackWorker


# the file tree shows at least 8 rows at the window's minimum size (spec G-1)
TREE_MINIMUM_HEIGHT = 224
# "Copy as Markdown" refuses anything larger; a file package is the way for those
CLIPBOARD_LIMIT = 200 * 1024


def asset_path(relative_path):
    # this is needed so the icon is still found when packaged into an exe
    # pyinstaller unpacks things into a temp folder, _MEIPASS is its path
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        # running from source: codepacker/ui/main_window.py is three levels below the root
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)


def open_folder(path):
    # open the folder in the system's file manager
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True
    except Exception:
        return False


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # this is where we keep the current state
        self.entries = []             # the files that can go in
        self.selection = SelectionModel()   # which of them are checked, the only place
        self.exclusions = []          # what the scan left out, and why (core.Exclusion)
        self.scanned_root = ""        # the folder the current file list comes from
        self.selection_paths = None   # the dropped or chosen files of an ad-hoc package
        self.busy = False             # scanning or packing
        self.last_output_dir = ""
        self.scan_worker = None
        self.pack_worker = None
        self.about_dialog = None

        self.settings = Settings()

        self.setWindowTitle(APP_NAME)
        self.resize(1240, 820)
        self.setMinimumSize(QSize(1020, 680))
        self.setAcceptDrops(True)

        # set the icon, if the file is there
        icon_path = asset_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet(theme.stylesheet())

        self.build_menu()
        self.build_ui()
        self.restore_settings()

        self.log_message("hi, drag a project folder here or click Browse folder")

    # ============================================================
    # BUILDING THE INTERFACE
    # ============================================================

    def build_menu(self):
        # a simple menu bar, nothing overcomplicated
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        self.open_action = QAction("Open project folder", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.choose_project_folder)
        file_menu.addAction(self.open_action)

        self.rescan_action = QAction("Rescan", self)
        self.rescan_action.setShortcut("F5")
        self.rescan_action.triggered.connect(self.start_scan)
        file_menu.addAction(self.rescan_action)

        self.build_action = QAction("Build package", self)
        self.build_action.setShortcut("Ctrl+B")
        self.build_action.triggered.connect(self.start_pack)
        file_menu.addAction(self.build_action)

        self.clear_recent_action = QAction("Clear recent folders", self)
        self.clear_recent_action.triggered.connect(self.clear_recent_folders)
        file_menu.addAction(self.clear_recent_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("What is this?", self)
        about_action.triggered.connect(self.show_about_box)
        help_menu.addAction(about_action)

    def build_ui(self):
        # the main widget that holds everything
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(8)

        layout.addWidget(self.build_top_bar())
        layout.addWidget(self.build_settings_card())
        layout.addWidget(self.build_middle_section(), 1)
        layout.addWidget(self.build_bottom_section())

        # status bar at the very bottom, with the signature on its right end
        self.statusBar().showMessage("ready")
        self.size_label = QLabel("")
        self.size_label.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.size_label)
        self.signature_button = SignatureButton()
        self.signature_button.clicked.connect(self.show_about_dialog)
        self.statusBar().addPermanentWidget(self.signature_button)

    def build_top_bar(self):
        # the app's mark and the project folder, in one row
        card = QFrame()
        card.setObjectName("card")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)

        icon_label = QLabel()
        icon_path = asset_path(os.path.join("assets", "icon_256.png"))
        if os.path.exists(icon_path):
            icon_label.setPixmap(QPixmap(icon_path).scaled(
                28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.setAccessibleName(APP_NAME)
        row.addWidget(icon_label)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        row.addWidget(title)
        row.addSpacing(10)

        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("Project folder: drag it here or click Browse folder")
        self.project_edit.setAccessibleName("Project folder")
        self.project_edit.setToolTip("The project folder; press Enter to scan it")
        self.project_edit.returnPressed.connect(self.start_scan)
        self.project_edit.textEdited.connect(self.forget_selection)
        row.addWidget(self.project_edit, 1)

        self.browse_button = QPushButton("Browse folder…")
        self.browse_button.setToolTip("Choose the project folder (Ctrl+O)")
        self.browse_button.clicked.connect(self.choose_project_folder)
        row.addWidget(self.browse_button)

        self.browse_files_button = QPushButton("Browse files…")
        self.browse_files_button.setToolTip("Choose some files for an ad-hoc package")
        self.browse_files_button.clicked.connect(self.choose_files)
        row.addWidget(self.browse_files_button)

        # the recent-folders dropdown
        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumWidth(150)
        self.recent_combo.setToolTip("Recent project folders")
        self.recent_combo.currentIndexChanged.connect(self.on_recent_folder_chosen)
        row.addWidget(self.recent_combo)

        return card

    def build_settings_card(self):
        # what and how to build, folded away until needed (spec G-1)
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.settings_toggle = QToolButton()
        self.settings_toggle.setObjectName("toggle")
        self.settings_toggle.setText("Settings")
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.settings_toggle.setArrowType(Qt.RightArrow)
        self.settings_toggle.setToolTip("Show or hide the settings")
        self.settings_toggle.toggled.connect(self.show_settings)
        header.addWidget(self.settings_toggle)
        settings_hint = QLabel("formats, part size, size limit, exclude patterns, output folder")
        settings_hint.setObjectName("muted")
        header.addWidget(settings_hint)
        header.addStretch(1)
        layout.addLayout(header)

        # two rows of settings, each laid out on its own so neither widens the other
        self.settings_body = QWidget()
        body = QVBoxLayout(self.settings_body)
        body.setContentsMargins(4, 0, 0, 6)
        body.setSpacing(6)
        formats = QHBoxLayout()
        formats.setSpacing(10)
        places = QHBoxLayout()
        places.setSpacing(10)
        body.addLayout(formats)
        body.addLayout(places)

        # the two output formats
        self.md_checkbox = QCheckBox("MD file")
        self.md_checkbox.setChecked(True)
        self.md_checkbox.setToolTip("One Markdown file with the file tree and every file; "
                                    "AI chats accept it")
        self.md_checkbox.stateChanged.connect(self.update_summary)
        formats.addWidget(self.md_checkbox)

        self.b64_checkbox = QCheckBox("Base64 zip TXT")
        self.b64_checkbox.setToolTip("Fallback: a zip as base64 text, for chats with a code "
                                     "sandbox")
        self.b64_checkbox.stateChanged.connect(self.update_summary)
        formats.addWidget(self.b64_checkbox)
        formats.addSpacing(12)

        # splitting, by size: no part gets larger than this (unless a single file is)
        self.split_checkbox = QCheckBox("Split into parts")
        self.split_checkbox.setToolTip("Split the MD into parts no larger than the max part size")
        self.split_checkbox.stateChanged.connect(self.update_summary)
        formats.addWidget(self.split_checkbox)
        formats.addWidget(QLabel("Max part size"))
        self.part_size_spin = QSpinBox()
        self.part_size_spin.setRange(50, 100000)
        self.part_size_spin.setSingleStep(100)
        self.part_size_spin.setValue(1000)
        self.part_size_spin.setSuffix(" kB")
        self.part_size_spin.setAccessibleName("Max part size")
        self.part_size_spin.setToolTip("No MD part gets larger than this, unless a single file is")
        self.part_size_spin.valueChanged.connect(self.update_summary)
        formats.addWidget(self.part_size_spin)
        formats.addSpacing(12)

        # max file size
        formats.addWidget(QLabel("Max file size"))
        self.max_kb_spin = QSpinBox()
        self.max_kb_spin.setRange(5, 20000)
        self.max_kb_spin.setSingleStep(50)
        self.max_kb_spin.setValue(300)
        self.max_kb_spin.setSuffix(" kB")
        self.max_kb_spin.setAccessibleName("Max file size")
        self.max_kb_spin.setToolTip("Larger files are skipped, they would just waste space")
        formats.addWidget(self.max_kb_spin)
        formats.addStretch(1)

        # extra exclude patterns
        places.addWidget(QLabel("Also exclude"))
        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("globs, e.g. *.bak, docs/**, tests/")
        self.exclude_edit.setAccessibleName("Also exclude")
        self.exclude_edit.setToolTip("Comma-separated globs; secrets, junk folders and binary "
                                     "files are always excluded")
        places.addWidget(self.exclude_edit, 1)
        places.addSpacing(12)

        # where the package goes
        places.addWidget(QLabel("Output folder"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("empty: a _codepacker folder next to the project")
        self.output_edit.setAccessibleName("Output folder")
        places.addWidget(self.output_edit, 1)
        self.output_browse_button = QPushButton("Browse\u2026")
        self.output_browse_button.setToolTip("Choose where the package is written")
        self.output_browse_button.clicked.connect(self.choose_output_folder)
        places.addWidget(self.output_browse_button)

        layout.addWidget(self.settings_body)
        self.settings_body.setVisible(False)

        return card

    def show_settings(self, expanded):
        self.settings_body.setVisible(expanded)
        self.settings_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def build_middle_section(self):
        # the file tree on the left, the log, statistics and exclusions on the right
        splitter = QSplitter(Qt.Horizontal)

        splitter.addWidget(self.build_tree_panel())
        splitter.addWidget(self.build_side_panel())

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 460])
        splitter.setChildrenCollapsible(False)

        return splitter

    def build_tree_panel(self):
        # the files in a tree, folders first
        card = QFrame()
        card.setObjectName("card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        # top row with the title and the scan button
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        heading = QLabel("Files")
        heading.setObjectName("section")
        top_row.addWidget(heading)
        top_row.addStretch(1)

        self.scan_button = QPushButton("Scan")
        self.scan_button.setObjectName("flat")
        self.scan_button.setToolTip("Scan the project folder (F5, or Enter in the folder field)")
        self.scan_button.clicked.connect(self.start_scan)
        top_row.addWidget(self.scan_button)

        select_all_button = QPushButton("Select all")
        select_all_button.setObjectName("flat")
        select_all_button.setToolTip("Check every file the filter shows")
        select_all_button.clicked.connect(self.select_all)
        top_row.addWidget(select_all_button)

        select_none_button = QPushButton("Select none")
        select_none_button.setObjectName("flat")
        select_none_button.setToolTip("Uncheck every file the filter shows")
        select_none_button.clicked.connect(self.select_none)
        top_row.addWidget(select_none_button)

        layout.addLayout(top_row)

        # search field above the tree; it filters 150 ms after the last key press
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(150)
        self.filter_timer.timeout.connect(self.apply_filter)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name, e.g. .py or render")
        self.filter_edit.setAccessibleName("Filter")
        self.filter_edit.textChanged.connect(self.on_filter_changed)
        layout.addWidget(self.filter_edit)

        # the tree itself: it only shows the selection model, folders first
        self.file_model = FileTreeModel(self.selection, self.on_selection_changed, self)
        self.tree = QTreeView()
        self.tree.setModel(self.file_model)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(TREE_MINIMUM_HEIGHT)
        self.tree.setAccessibleName("Files")
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 84)
        self.tree_fade = attach_scroll_fade(self.tree, theme.COLORS["background_light"])
        layout.addWidget(self.tree, 1)

        return card

    def build_side_panel(self):
        # the log, the statistics and the exclusions, one tab each
        card = QFrame()
        card.setObjectName("card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)

        self.side_tabs = QTabWidget()
        self.side_tabs.setUsesScrollButtons(False)   # every tab stays visible

        # log tab
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(6, 6, 6, 6)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAccessibleName("Log")
        self.log_fade = attach_scroll_fade(self.log_view, theme.COLORS["log_background"])
        log_layout.addWidget(self.log_view)

        log_buttons = QHBoxLayout()
        log_buttons.addStretch(1)
        clear_log_button = QPushButton("Clear log")
        clear_log_button.setObjectName("flat")
        clear_log_button.setToolTip("Empty the log")
        clear_log_button.clicked.connect(self.log_view.clear)
        log_buttons.addWidget(clear_log_button)
        log_layout.addLayout(log_buttons)

        self.side_tabs.addTab(log_tab, "Log")

        # statistics tab
        self.stats_tree = QTreeWidget()
        self.stats_tree.setColumnCount(3)
        self.stats_tree.setHeaderLabels(["Type", "Count", "Size"])
        self.stats_tree.setRootIsDecorated(False)
        self.stats_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.stats_fade = attach_scroll_fade(self.stats_tree, theme.COLORS["background_light"])
        self.side_tabs.addTab(self.stats_tree, "Statistics")

        # what the scan left out, each with its reason and rule
        self.excluded_tree = QTreeWidget()
        self.excluded_tree.setColumnCount(3)
        self.excluded_tree.setHeaderLabels(["Path", "Reason", "Rule"])
        self.excluded_tree.setRootIsDecorated(False)
        self.excluded_tree.setUniformRowHeights(True)
        self.excluded_tree.setColumnWidth(0, 200)
        self.excluded_tree.setColumnWidth(1, 220)
        self.excluded_fade = attach_scroll_fade(self.excluded_tree, theme.COLORS["background_light"])
        self.side_tabs.addTab(self.excluded_tree, "Excluded")

        layout.addWidget(self.side_tabs)

        return card

    def build_bottom_section(self):
        # the summary, the big buttons and the progress bar
        section = QWidget()

        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # the summary and the estimated sizes, in one line
        summary_row = QHBoxLayout()
        summary_row.setSpacing(16)
        self.summary_label = QLabel("Nothing scanned yet")
        self.summary_label.setObjectName("summary")
        summary_row.addWidget(self.summary_label)
        self.estimate_label = QLabel("")
        self.estimate_label.setObjectName("muted")
        summary_row.addWidget(self.estimate_label)
        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        # button row
        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.build_button = QPushButton("Build package")
        self.build_button.setObjectName("primary")
        self.build_button.setToolTip("Build the package from the checked files (Ctrl+B)")
        self.build_button.clicked.connect(self.start_pack)
        buttons.addWidget(self.build_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Stop the scan or the build; a stopped build leaves "
                                      "nothing behind")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)

        buttons.addStretch(1)

        self.copy_markdown_button = QPushButton("Copy as Markdown")
        self.copy_markdown_button.setToolTip("Put the Markdown of the checked files on the "
                                             "clipboard (up to 200 kB)")
        self.copy_markdown_button.clicked.connect(self.copy_as_markdown)
        buttons.addWidget(self.copy_markdown_button)

        open_folder_button = QPushButton("Open output folder")
        open_folder_button.setToolTip("Show the package in the file manager")
        open_folder_button.clicked.connect(self.open_output_folder)
        buttons.addWidget(open_folder_button)

        copy_path_button = QPushButton("Copy path")
        copy_path_button.setToolTip("Copy the output folder's path to the clipboard")
        copy_path_button.clicked.connect(self.copy_output_path)
        buttons.addWidget(copy_path_button)

        layout.addLayout(buttons)

        # progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        return section

    # ============================================================
    # DRAG AND DROP, SO THE FOLDER CAN BE DROPPED IN
    # ============================================================

    def dragEnterEvent(self, event):
        # only local files and folders, and not while busy (spec C-17)
        local = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if local and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        # one folder is a project; files (or several things) make an ad-hoc package
        if self.busy:
            event.ignore()
            return
        dropped = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        dropped = [path for path in dropped if os.path.exists(path)]
        if len(dropped) == 1 and os.path.isdir(dropped[0]):
            self.selection_paths = None
            self.project_edit.setText(dropped[0])
            self.log_message("dropped: " + dropped[0])
            self.start_scan()
        elif dropped:
            self.start_selection_scan(dropped)

    # ============================================================
    # EVENT HANDLERS
    # ============================================================

    def log_message(self, text):
        # write a line to the log
        self.log_view.appendPlainText(text)

    def show_about_box(self):
        QMessageBox.information(
            self,
            APP_NAME,
            "This app turns a programming project folder into a file that "
            "can be uploaded to an AI chat.\n\n"
            "Many chats don't allow zip uploads, so there are two options instead:\n\n"
            "1. MD file - every source file in a single text file, together "
            "with the file structure. This is the recommended one.\n\n"
            "2. Base64 zip TXT - the zip encoded as text. An LLM with a code "
            "sandbox can decode and unzip it there.\n\n"
            "Secret files (.env, keys) are never included."
        )

    def show_about_dialog(self):
        # the signature's card: a popup, it closes on X, Esc or a click outside
        self.about_dialog = AboutDialog(self)
        self.about_dialog.show()

    def choose_project_folder(self):
        start_dir = self.project_edit.text().strip()
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")

        chosen = QFileDialog.getExistingDirectory(
            self, "Choose the project folder", start_dir)

        if chosen:
            self.selection_paths = None
            self.project_edit.setText(chosen)
            self.log_message("project folder: " + chosen)
            # scan it right away once chosen, it's more convenient this way
            self.start_scan()

    def choose_files(self):
        start_dir = self.project_edit.text().strip()
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")
        chosen, _ = QFileDialog.getOpenFileNames(self, "Choose the files to pack", start_dir)
        if chosen:
            self.start_selection_scan(chosen)

    def start_selection_scan(self, chosen):
        # an ad-hoc package: just these, relative to their common parent folder
        self.selection_paths = list(chosen)
        self.project_edit.setText(os.path.commonpath(
            [os.path.dirname(core.clean_path(path)) for path in chosen]))
        self.log_message("ad-hoc package: {} chosen".format(core.plural(len(chosen), "item")))
        self.start_scan()

    def forget_selection(self, text):
        # a folder typed into the field is a project again
        self.selection_paths = None

    def choose_output_folder(self):
        start_dir = self.output_edit.text().strip()
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")

        chosen = QFileDialog.getExistingDirectory(
            self, "Choose where to save the package", start_dir)

        if chosen:
            self.output_edit.setText(chosen)

    def on_recent_folder_chosen(self, index):
        # a previous folder was chosen from the dropdown
        if index <= 0:
            return
        path = self.recent_combo.itemText(index)
        if os.path.isdir(path):
            self.selection_paths = None
            self.project_edit.setText(path)
            self.start_scan()
        else:
            self.log_message("this folder no longer exists: " + path)
            # reloading the list drops it and puts the dropdown back on its first item
            self.refresh_recent_folders()

    # ============================================================
    # THE SCAN
    # ============================================================

    def start_scan(self):
        if self.busy:
            return

        root = self.project_edit.text().strip()
        if self.selection_paths:
            root = os.path.commonpath([os.path.dirname(core.clean_path(path))
                                       for path in self.selection_paths])

        if root == "" or not os.path.isdir(root):
            QMessageBox.warning(self, APP_NAME,
                                "Please choose an existing project folder first.")
            return

        self.entries = []
        self.exclusions = []
        self.fill_tree()
        self.scanned_root = core.clean_path(root)

        self.progress_bar.setRange(0, 0)      # 0,0 means it spins indefinitely
        self.set_busy(True)
        self.statusBar().showMessage("scanning...")
        self.log_message("starting scan: " + root)

        # spec S-4: a package written inside the project would be scanned in again next time
        output_dir = self.output_dir_for(root)
        if core.relative_inside(output_dir, root) is not None:
            self.log_message("warning: the output folder is inside the project, "
                             "the scan leaves it out")

        self.scan_worker = ScanWorker(
            root,
            self.max_kb_spin.value(),
            self.exclude_edit.text(),
            output_dir,
            self.selection_paths,
        )
        self.scan_worker.log_line.connect(self.log_message)
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.done.connect(self.on_scan_done)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.start()

    def max_part_bytes(self):
        # 0 when the MD is not split
        if not self.split_checkbox.isChecked():
            return 0
        return self.part_size_spin.value() * 1024

    def current_project_name(self):
        root = self.scanned_root or self.project_edit.text().strip()
        return core.project_name(root) if root else "project"

    def output_dir_for(self, root):
        # the folder the package goes to: the one chosen, or <project>_codepacker next to it
        chosen = self.output_edit.text().strip()
        if chosen == "":
            return core.default_output_dir(root)
        return core.clean_path(chosen)

    def on_scan_progress(self, checked, found):
        self.statusBar().showMessage(
            "scanning... {} files checked, {} usable".format(checked, found))

    def on_scan_done(self, result):
        # only the included files become tree items; whatever a rule left out (secret files
        # above all) is never offered for selection
        self.entries = result.included
        self.exclusions = result.excluded
        self.scanned_root = result.root

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.set_busy(False)

        self.fill_tree()
        self.fill_excluded()

        if result.cancelled:
            # a partial list must not be packed by mistake
            self.build_button.setEnabled(False)
            self.log_message("scan cancelled, {} found so far".format(
                core.plural(len(self.entries), "usable file")))
            self.statusBar().showMessage("cancelled \u2013 partial list")
            return

        self.log_message("scan complete, {}".format(core.plural(len(self.entries), "usable file")))
        self.statusBar().showMessage("scan complete")

        # save the folder into the recent list (an ad-hoc package is no project)
        if self.selection_paths is None and os.path.isdir(self.scanned_root):
            self.fill_recent_combo(self.settings.add_recent_folder(self.scanned_root))

        if len(self.entries) == 0:
            QMessageBox.information(
                self, APP_NAME,
                "No uploadable source files were found in this folder.\n\n"
                "The max file size might be too strict, or the exclude "
                "patterns filtered everything out.")

    def set_busy(self, busy):
        # while scanning or packing: no other folder, no new scan and no new build
        self.busy = busy
        for control in (self.open_action, self.rescan_action, self.build_action,
                        self.clear_recent_action, self.browse_button, self.browse_files_button,
                        self.output_browse_button, self.recent_combo, self.scan_button,
                        self.build_button, self.copy_markdown_button):
            control.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def cancel_work(self):
        for worker in (self.scan_worker, self.pack_worker):
            if worker is not None and worker.isRunning():
                worker.cancel()
                self.log_message("cancel requested, stopping shortly")

    def on_scan_failed(self, message):
        self.log_message("ERROR: " + message)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.set_busy(False)
        QMessageBox.critical(self, APP_NAME, "Something went wrong:\n\n" + message)

    # ============================================================
    # MANAGING THE FILE TREE
    # ============================================================

    def fill_tree(self):
        # a new file list: everything checked, the tree shows it through the selection model
        self.selection = SelectionModel(self.entries)
        self.file_model.set_selection(self.selection)
        self.tree.expandAll()
        self.on_selection_changed()

    def fill_excluded(self):
        # every file or folder the scan left out, with its reason and rule
        self.excluded_tree.clear()
        for exclusion in self.exclusions:
            item = QTreeWidgetItem(self.excluded_tree)
            item.setText(0, exclusion.rel_path)
            item.setText(1, exclusion.reason)
            item.setText(2, exclusion.rule_id)
            item.setToolTip(0, exclusion.rel_path)
        self.side_tabs.setTabText(2, "Excluded ({})".format(len(self.exclusions)))

    def on_selection_changed(self):
        self.update_summary()
        self.update_statistics()

    def select_all(self):
        self.set_visible_checked(True)

    def select_none(self):
        self.set_visible_checked(False)

    def set_visible_checked(self, checked):
        # only the rows the filter shows: a hidden file keeps its check mark
        self.file_model.set_checked(self.file_model.visible_paths(), checked)

    def on_filter_changed(self, text):
        # filter once the typing stops, not on every key press
        self.filter_timer.start()

    def apply_filter(self):
        self.file_model.set_filter(self.filter_edit.text())
        self.tree.expandAll()

    # ============================================================
    # SUMMARY AND STATISTICS
    # ============================================================

    def selected_entries(self):
        # the checked files, in scan order: exactly what the package gets
        return self.selection.checked_entries()

    def update_summary(self):
        # work out how many files are going in and roughly how big it'll be
        selected = self.selected_entries()

        total_size = 0
        for entry in selected:
            total_size = total_size + entry.size

        self.summary_label.setText(
            "{} of {} selected, raw text: {}".format(
                len(selected), core.plural(len(self.entries), "file"),
                core.format_size(total_size)))

        if len(selected) == 0:
            self.estimate_label.setText("")
            self.size_label.setText("")
            return

        md_estimate, b64_estimate = core.estimate_sizes(selected, self.current_project_name())
        self.size_label.setText("MD ~{} \u00b7 ~{} tokens".format(
            core.format_size(md_estimate), format(core.estimate_tokens(md_estimate), ",")))

        parts = []

        if self.md_checkbox.isChecked():
            text = "MD ~" + core.format_size(md_estimate)
            max_part_bytes = self.max_part_bytes()
            if max_part_bytes and md_estimate > max_part_bytes:
                text = text + " in ~{} parts".format(math.ceil(md_estimate / max_part_bytes))
            parts.append(text)

        if self.b64_checkbox.isChecked():
            parts.append("base64 txt ~" + core.format_size(b64_estimate))

        text = "Estimated size: " + ",   ".join(parts)

        # warn if it's going to be large
        if self.md_checkbox.isChecked() and not self.max_part_bytes():
            if md_estimate > 2 * 1024 * 1024:
                text = text + "   |   that's a lot for one file, consider splitting it into parts"

        self.estimate_label.setText(text)

    def update_statistics(self):
        # show a breakdown by extension
        self.stats_tree.clear()

        selected = self.selected_entries()
        rows = core.extension_stats(selected)

        for extension, count, size in rows:
            item = QTreeWidgetItem(self.stats_tree)
            item.setText(0, extension)
            item.setText(1, str(count))
            item.setText(2, core.format_size(size))
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)

    # ============================================================
    # BUILDING THE PACKAGE
    # ============================================================

    def start_pack(self):
        if self.busy:
            return

        # the folder the file list comes from, even if the field was edited since
        root = self.scanned_root

        if root == "" or not os.path.isdir(root):
            QMessageBox.warning(self, APP_NAME, "Please scan a project folder first.")
            return

        selected = self.selected_entries()

        if len(selected) == 0:
            QMessageBox.warning(self, APP_NAME, "No files are selected.")
            return

        if not self.md_checkbox.isChecked() and not self.b64_checkbox.isChecked():
            QMessageBox.warning(self, APP_NAME, "Choose at least one output format.")
            return

        # figure out where to save; a trailing slash or backslash keeps the name (spec C-18)
        project_name = core.project_name(root)
        output_dir = self.output_dir_for(root)
        if core.real_path(output_dir) == core.real_path(root):
            QMessageBox.warning(self, APP_NAME,
                                "The output folder can't be the project folder itself.")
            return

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, APP_NAME,
                                 "Can't create the output folder:\n" + str(error))
            return

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.set_busy(True)
        self.statusBar().showMessage("building package...")
        self.log_message("starting package build, {} file(s)".format(len(selected)))

        self.pack_worker = PackWorker(
            project_name,
            selected,
            output_dir,
            self.md_checkbox.isChecked(),
            self.b64_checkbox.isChecked(),
            self.max_part_bytes(),
            root,
        )
        self.pack_worker.log_line.connect(self.log_message)
        self.pack_worker.progress.connect(self.on_pack_progress)
        self.pack_worker.done.connect(self.on_pack_done)

        self.last_output_dir = output_dir
        self.pack_worker.start()

    def on_pack_progress(self, done, total):
        # 100 % only once everything is written without an error (on_pack_done)
        if total > 0:
            self.progress_bar.setValue(min(99, int(done * 100 / total)))

    def on_pack_done(self, results):
        # results: one core.BundleResult per format, None when the build was cancelled
        self.set_busy(False)

        if results is None:
            self.progress_bar.setValue(0)
            self.statusBar().showMessage("cancelled, the partial output was deleted")
            return

        failed = any(not result.ok for result in results)
        status = "finished with errors" if failed else "finished"
        if not failed:
            self.progress_bar.setValue(100)
        self.statusBar().showMessage(status)

        lines = []
        has_large_file = False
        for result in results:
            for path in result.paths:
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                lines.append("{}  -  {}".format(os.path.basename(path), core.format_size(size)))
                if size > 2 * 1024 * 1024:
                    has_large_file = True

        message = status[0].upper() + status[1:] + ":\n\n"
        message = message + "\n".join(result.line for result in results)
        if lines:
            message = message + "\n\nFiles:\n" + "\n".join(lines)
        message = message + "\n\nLocation:\n" + self.last_output_dir

        if has_large_file:
            message = message + ("\n\nNote: one of the files is over 2 MB, "
                                 "consider splitting it into parts.")

        # save the settings for next time
        self.save_settings()

        if failed:
            QMessageBox.warning(self, APP_NAME, message)
        else:
            QMessageBox.information(self, APP_NAME, message)

    def copy_as_markdown(self):
        # the MD of the checked files on the clipboard, without writing anything
        selected = self.selected_entries()
        if len(selected) == 0:
            QMessageBox.warning(self, APP_NAME, "No files are selected.")
            return
        project_name = core.project_name(self.scanned_root)
        size, _ = core.estimate_sizes(selected, project_name)
        text = None
        if size <= CLIPBOARD_LIMIT:
            text, _ = core.markdown_text(project_name, selected, self.log_message,
                                         self.scanned_root)
            size = len(text.encode("utf-8"))
        if text is None or size > CLIPBOARD_LIMIT:
            QMessageBox.information(
                self, APP_NAME,
                "The Markdown would be about {}, more than the {} the clipboard takes.\n\n"
                "Build a file package instead (Ctrl+B).".format(
                    core.format_size(size), core.format_size(CLIPBOARD_LIMIT)))
            return
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage("copied as Markdown: {}, ~{} tokens".format(
            core.format_size(size), format(core.estimate_tokens(len(text)), ",")))

    def open_output_folder(self):
        target = self.last_output_dir
        if target == "":
            target = self.output_edit.text().strip()

        if target == "" or not os.path.isdir(target):
            QMessageBox.information(self, APP_NAME,
                                    "There's no output folder yet, build a package first.")
            return

        if not open_folder(target):
            QMessageBox.information(self, APP_NAME, "Couldn't open:\n" + target)

    def copy_output_path(self):
        from PySide6.QtWidgets import QApplication

        target = self.last_output_dir
        if target == "":
            target = self.output_edit.text().strip()

        if target == "":
            QMessageBox.information(self, APP_NAME, "Nothing to copy yet.")
            return

        QApplication.clipboard().setText(target)
        self.statusBar().showMessage("path copied to clipboard")

    # ============================================================
    # SAVING AND RESTORING SETTINGS
    # ============================================================

    def restore_settings(self):
        # restore the previous state so it doesn't need to be set up every time
        self.md_checkbox.setChecked(self.settings.read("md_enabled", True))
        self.b64_checkbox.setChecked(self.settings.read("b64_enabled", False))
        self.split_checkbox.setChecked(self.settings.read("split_parts", False))
        self.part_size_spin.setValue(self.settings.read("max_part_kb", 1000))
        self.max_kb_spin.setValue(self.settings.read("max_kb", 300))
        self.exclude_edit.setText(self.settings.read("extra_excludes", ""))
        self.output_edit.setText(self.settings.read("output_dir", ""))
        self.settings_toggle.setChecked(self.settings.read("settings_expanded", False))

        # fill in the last folder right away, but don't scan it automatically
        recent = self.settings.recent_folders()
        self.fill_recent_combo(recent)
        if len(recent) > 0:
            self.project_edit.setText(recent[0])

    def refresh_recent_folders(self):
        # one look at the disk per refresh: the folders that are gone drop out
        self.fill_recent_combo(self.settings.recent_folders())

    def fill_recent_combo(self, folders):
        self.recent_combo.blockSignals(True)
        self.recent_combo.clear()
        self.recent_combo.addItem("recent folders...")
        for path in folders:
            self.recent_combo.addItem(path)
        self.recent_combo.setCurrentIndex(0)
        self.recent_combo.blockSignals(False)

    def clear_recent_folders(self):
        self.settings.clear_recent_folders()
        self.settings.save()
        self.fill_recent_combo([])
        self.log_message("recent folders cleared")

    def save_settings(self):
        self.settings.write("md_enabled", self.md_checkbox.isChecked())
        self.settings.write("b64_enabled", self.b64_checkbox.isChecked())
        self.settings.write("split_parts", self.split_checkbox.isChecked())
        self.settings.write("max_part_kb", self.part_size_spin.value())
        self.settings.write("max_kb", self.max_kb_spin.value())
        self.settings.write("extra_excludes", self.exclude_edit.text())
        self.settings.write("output_dir", self.output_edit.text())
        self.settings.write("settings_expanded", self.settings_toggle.isChecked())
        self.settings.save()

    def closeEvent(self, event):
        # save the settings; a running scan or build is cancelled and waited for, so no
        # thread outlives the window
        self.save_settings()

        for worker in (self.scan_worker, self.pack_worker):
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait()

        event.accept()

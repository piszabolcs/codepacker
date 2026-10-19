# -*- coding: utf-8 -*-
#
# this is where the background threads live
# a separate thread is needed, otherwise the window would freeze while working
# QThread sends signals back to the main thread, which we subscribe to

import os

from PySide6.QtCore import QThread, Signal

from . import core


class ScanWorker(QThread):
    # this thread walks the project folder

    # these signals talk back to the main thread
    log_line = Signal(str)          # one log line
    progress = Signal(int, int)     # how many files checked, how many are good
    done = Signal(object)           # the core.ScanResult at the end (cancelled: partial)
    failed = Signal(str)            # if something crashed

    def __init__(self, root, max_kb, extra_excludes, output_dir=None, selection=None):
        super().__init__()
        self.root = root
        self.selection = selection      # files and folders of an ad-hoc package, or None
        self.max_kb = max_kb
        self.extra_excludes = extra_excludes
        self.output_dir = output_dir
        self.cancelled = False

    def cancel(self):
        # called by the main thread when the user clicks the cancel button
        self.cancelled = True

    def run(self):
        # this runs in the background
        try:
            scan = core.scan_project
            target = self.root
            if self.selection:
                scan = core.scan_selection
                target = self.selection
            result = scan(
                target,
                self.max_kb,
                self.extra_excludes,
                log=self.log_line.emit,
                progress=self.progress.emit,
                should_stop=lambda: self.cancelled,
                output_dir=self.output_dir,
            )
            self.done.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class PackWorker(QThread):
    # this thread writes out the finished files

    log_line = Signal(str)
    progress = Signal(int, int)
    done = Signal(object)           # [core.BundleResult], one per format; None when cancelled

    def __init__(self, project_name, entries, output_dir,
                 md_enabled, b64_enabled, max_part_bytes, root=None):
        super().__init__()
        self.root = root                # the project folder: the bundle checks every file
        self.project_name = project_name
        self.entries = entries
        self.output_dir = output_dir
        self.md_enabled = md_enabled
        self.b64_enabled = b64_enabled
        self.max_part_bytes = max_part_bytes      # 0: the MD is one file
        self.cancelled = False

    def cancel(self):
        # the build stops before the next file and deletes what it has written
        self.cancelled = True

    def run(self):
        self.log_line.emit("building the package...")
        try:
            results = core.build_package(
                self.project_name,
                self.entries,
                self.output_dir,
                md=self.md_enabled,
                b64=self.b64_enabled,
                max_part_bytes=self.max_part_bytes,
                root=self.root,
                progress=self.progress.emit,
                log=self.log_line.emit,
                should_stop=lambda: self.cancelled,
            )
        except core.Cancelled:
            self.log_line.emit("cancelled, the partial output was deleted")
            self.done.emit(None)
            return

        for result in results:
            for path in result.paths:
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                self.log_line.emit("done: {} ({})".format(
                    os.path.basename(path), core.format_size(size)))
            self.log_line.emit(result.line)
        self.done.emit(results)

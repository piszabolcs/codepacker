# -*- coding: utf-8 -*-
#
# application start-up: create the QApplication and show the main window
# main.py (the entry point) calls run()

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from .. import APP_NAME
from .main_window import MainWindow, asset_path

# the app's identity for the windows taskbar; version-free, so pinned shortcuts survive updates
APP_USER_MODEL_ID = "psz." + APP_NAME


def run():
    # on windows this is needed so our own icon shows up in the taskbar
    # instead of python's default icon
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    # no organization name on purpose: the settings use their own INI file (settings.py), and
    # without one a default-constructed QSettings anywhere cannot write to the registry
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # set the icon for the whole application
    icon_path = asset_path(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    # the exit code of the event loop, main.py passes it to sys.exit()
    return app.exec()

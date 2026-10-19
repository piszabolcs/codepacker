"""Shared pytest setup: offscreen Qt, temp settings (per session and per test), tree helper."""

import atexit
import os
import shutil
import tempfile

# Never open a window on screen: Qt reads this when the QApplication is created. Assigned, not
# defaulted, so a QT_QPA_PLATFORM set in the developer's shell cannot bring a window up.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# The offscreen platform ships no fonts; the system's fonts give the real text widths that the
# layout tests measure (and silence Qt's missing-font-directory warning).
WINDOWS_FONTS = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
if os.path.isdir(WINDOWS_FONTS):
    os.environ.setdefault("QT_QPA_FONTDIR", WINDOWS_FONTS)

# Fail-safe under the per-test redirect below: from import time on, %APPDATA% and the settings
# file point into a throw-away folder for the whole session, so nothing that runs outside a test
# function (collection, module-level code) can reach the real %APPDATA%\CodePacker.
SESSION_FOLDER = tempfile.mkdtemp(prefix="codepacker-tests-")
atexit.register(shutil.rmtree, SESSION_FOLDER, ignore_errors=True)
os.environ["APPDATA"] = SESSION_FOLDER

import pytest  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from codepacker import settings  # noqa: E402
from fixtures import write_tree  # noqa: E402

settings.settings_file_override = os.path.join(SESSION_FOLDER, "CodePacker", "settings.ini")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path_factory, monkeypatch):
    """Point the app's settings file at a fresh path for every test and return it.

    Nothing reaches %APPDATA%\\CodePacker or the registry, and no state leaks from one test to
    the next. The folder does not exist yet: the app creates it on its first save, as in real use.
    """
    path = tmp_path_factory.mktemp("settings") / "CodePacker" / "settings.ini"
    monkeypatch.setattr(settings, "settings_file_override", str(path))
    return path


@pytest.fixture
def message_boxes(monkeypatch):
    """Record QMessageBox calls instead of opening modal dialogs, which would block the test.

    Each stub answers like a user who accepts: Ok for the notices, Yes for a question.
    """
    shown = []
    answers = {
        "information": QMessageBox.StandardButton.Ok,
        "warning": QMessageBox.StandardButton.Ok,
        "critical": QMessageBox.StandardButton.Ok,
        "question": QMessageBox.StandardButton.Yes,
    }
    for kind, answer in answers.items():

        def record(*args, _kind=kind, _answer=answer, **kwargs):
            shown.append((_kind, args[1:]))
            return _answer

        monkeypatch.setattr(QMessageBox, kind, staticmethod(record))
    return shown


@pytest.fixture
def make_project():
    """Return the helper ``make_project(root, {"relative/path": str | bytes}) -> root``."""
    return write_tree

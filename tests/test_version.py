"""The version is written down once, in codepacker/__init__.py, and the UI does not print it."""

import ast
import re
from pathlib import Path

from PySide6.QtWidgets import QLabel

import codepacker
from codepacker.ui import app
from codepacker.ui.main_window import MainWindow

REPO_ROOT = Path(__file__).resolve().parent.parent

# A quoted string that looks like a version number, e.g. "2.0", '3.0.0' or "v1.2".
VERSION_LITERAL = re.compile(r"""["']v?\d+\.\d+(\.\d+)*["']""")


def _sources():
    return [
        *sorted(REPO_ROOT.joinpath("codepacker").rglob("*.py")),
        REPO_ROOT / "main.py",
        REPO_ROOT / "codepacker.spec",
        *sorted(REPO_ROOT.glob("*.bat")),
    ]


def test_the_version_is_a_semantic_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", codepacker.__version__)


def test_the_version_is_written_down_only_in_the_package_init():
    hits = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _sources()
        if VERSION_LITERAL.search(path.read_text(encoding="utf-8"))
    ]
    assert hits == ["codepacker/__init__.py"]


def test_the_window_title_is_the_app_name_without_a_version(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "CodePacker"


def test_no_label_in_the_window_shows_a_version(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    texts = [label.text() for label in window.findChildren(QLabel)]
    assert [text for text in texts if re.search(r"\d+\.\d+", text)] == []


def test_the_app_user_model_id_is_version_free():
    assert app.APP_USER_MODEL_ID == "psz.CodePacker"
    assert not re.search(r"\d", app.APP_USER_MODEL_ID)


def test_the_exe_version_resource_is_generated_from_the_package_version():
    tree = ast.parse((REPO_ROOT / "codepacker.spec").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "codepacker"
        for alias in node.names
    }
    assert "__version__" in imported
    exe_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "EXE"
    ]
    assert exe_calls
    assert all("version" in {keyword.arg for keyword in call.keywords} for call in exe_calls)

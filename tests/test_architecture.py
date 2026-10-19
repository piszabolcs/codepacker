"""Architecture rules: the core package stays importable without Qt (Global Constraint 8)."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Run in a fresh interpreter (site-packages enabled, so PySide6 is installed there) that blocks
# PySide6 before importing every module of codepacker.core.
IMPORT_CORE_WITHOUT_PYSIDE6 = """
import pkgutil
import sys

sys.modules["PySide6"] = None  # from here on, any "import PySide6..." raises ImportError

import codepacker.core

for module in pkgutil.iter_modules(codepacker.core.__path__, "codepacker.core."):
    __import__(module.name)
"""


def test_core_imports_without_pyside6():
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_CORE_WITHOUT_PYSIDE6],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr

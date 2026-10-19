"""Language rules (Global Constraint 1): English sources, generic AI-chat wording."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The old product wording, assembled at runtime so this file does not contain it.
OLD_PRODUCT_WORD = "co" + "pilot"
HUNGARIAN_LETTERS = re.compile("[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")


def _app_sources():
    return [
        *sorted(REPO_ROOT.joinpath("codepacker").rglob("*.py")),
        REPO_ROOT / "main.py",
        REPO_ROOT / "codepacker.spec",
        *sorted(REPO_ROOT.glob("*.bat")),
    ]


def _hits(paths, matches):
    return [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{number}"
        for path in paths
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if matches(line)
    ]


def test_the_app_sources_contain_no_hungarian_letters():
    assert _hits(_app_sources(), HUNGARIAN_LETTERS.search) == []


def test_no_file_uses_the_old_product_wording():
    # the plan document describes this very rename, so it is the one place that may name it
    paths = [
        *_app_sources(),
        *sorted(REPO_ROOT.joinpath("tests").rglob("*.py")),
        *sorted(REPO_ROOT.joinpath(".github").rglob("*.yml")),
        REPO_ROOT / "README.md",
        REPO_ROOT / ".gitignore",
    ]
    assert _hits(paths, lambda line: OLD_PRODUCT_WORD in line.lower()) == []

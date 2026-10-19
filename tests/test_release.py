"""Release hygiene (spec 6.5, T-17, T-19): README images, notices, --version, the demo project."""

import re
import sys
from pathlib import Path

import codepacker
import main
from codepacker import core

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
import make_demo  # noqa: E402


def test_every_image_the_readme_shows_exists():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Local images (logo + screenshots) are HTML <img> tags; the badges are remote and skipped.
    images = [src for src in re.findall(r'<img src="([^"]+)"', readme) if not src.startswith("http")]
    assert len(images) >= 4
    assert [image for image in images if not (REPO_ROOT / image).is_file()] == []


def test_the_notices_and_the_changelog_are_there():
    notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Copyright 2026 Pintér Szabolcs" in notice
    assert "LGPL-3.0" in notice and "bootloader exception" in notice
    assert f"## [{codepacker.__version__}] " in (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_main_answers_version_without_a_window(capsys):
    assert main.main(["--version"]) == 0
    assert capsys.readouterr().out == f"CodePacker {codepacker.__version__}\n"


def test_the_demo_project_has_about_30_files_and_its_secrets_stay_out(tmp_path):
    root = make_demo.write_demo(tmp_path / "shop-app")
    assert 25 <= len([path for path in root.rglob("*") if path.is_file()]) <= 35
    result = core.scan_project(str(root), 300, "")
    secrets = sorted(e.rel_path for e in result.excluded if e.kind == "secret")
    assert secrets == [".env", "config/credentials.json", "keys/id_ed25519"]
    assert sorted(r.token_type for r in result.redactions) == ["github", "openai"]

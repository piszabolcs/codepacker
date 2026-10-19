"""Scan safety and exclusion transparency (spec S-3, S-4, S-5, C-8, C-9, C-13, C-15, C-18)."""

import os
import re
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from codepacker import core
from fixtures import LINK_OUTSIDE, LONG_PATH_FILE, LOOP_TO_ROOT, hostile_tree, long_path_safe

LOCK_FILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
              "Cargo.lock", "composer.lock", "go.sum"]


def _scan(root, excludes="", **kwargs):
    log = []
    return core.scan_project(str(root), 300, excludes, log=log.append, **kwargs), log


def _paths(result):
    return [entry.relative_path for entry in result.included]


@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions exist only on Windows")
def test_junctions_are_never_followed_and_every_file_really_lies_inside(tmp_path):
    root = hostile_tree(tmp_path / "project")
    if not os.path.isjunction(root / LINK_OUTSIDE):
        pytest.skip("mklink /J is not available on this machine")
    result, log = _scan(root)
    links = sorted((e.rel_path, e.kind) for e in result.excluded if e.kind == "link")
    assert links == [(LINK_OUTSIDE, "link"), (LOOP_TO_ROOT, "link")]
    included = _paths(result)
    assert [p for p in included if p.startswith((LINK_OUTSIDE, LOOP_TO_ROOT))] == []
    assert len(included) == len(set(included))
    real_root = os.path.realpath(root)
    for entry in result.included:
        real = os.path.realpath(long_path_safe(entry.full_path)).removeprefix("\\\\?\\")
        assert real.startswith(real_root + os.sep)
    assert f"skipped {LINK_OUTSIDE} — link or junction, not followed [link.not_followed]" in log


def test_the_default_output_is_next_to_the_project_whatever_it_ends_in(tmp_path):
    for typed in (str(tmp_path / "proj"), str(tmp_path / "proj") + "/",
                  str(tmp_path / "proj") + "\\"):
        assert core.project_name(typed) == "proj"
        assert core.default_output_dir(typed) == str(tmp_path / "proj_codepacker")


def test_the_output_folder_inside_the_project_is_left_out(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {"main.py": "x = 1\n", "bundles/proj.md": "# old\n"})
    result, _ = _scan(root, output_dir=str(root / "bundles") + "/")
    assert _paths(result) == ["main.py"]
    assert [(e.rel_path, e.kind) for e in result.excluded] == [("bundles", "self_output")]


def test_github_is_included_and_rules_ignore_letter_case(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {
        ".github/workflows/ci.yml": "on: push\n",
        "Node_Modules/x/index.js": "module.exports = 1;\n",
        "web/PACKAGE-LOCK.JSON": "{}\n",
        "src/app.py": "x = 1\n",
    })
    result, _ = _scan(root)
    assert _paths(result) == [".github/workflows/ci.yml", "src/app.py"]
    assert [(e.rel_path, e.kind) for e in result.excluded] == [
        ("Node_Modules", "junk_dir"), ("web/PACKAGE-LOCK.JSON", "lock")]


def test_lock_files_and_logs_are_excluded_by_their_kind(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {
        **{name: "x\n" for name in LOCK_FILES}, "app.log": "x\n", "app.log.1": "x\n"})
    result, _ = _scan(root)
    assert result.included == []
    assert {e.rel_path: e.kind for e in result.excluded} == {
        **{name: "lock" for name in LOCK_FILES}, "app.log": "log", "app.log.1": "log"}


def test_user_patterns_are_globs_not_substrings(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {
        "latest.py": "x = 1\n", "contest/entry.py": "x = 2\n", "teszt/a.py": "x = 3\n",
        "docs/guide/a.md": "# a\n", "notes.BAK": "old\n",
    })
    result, _ = _scan(root, "*.bak, docs/**, teszt")
    assert _paths(result) == ["contest/entry.py", "latest.py"]
    assert [(e.rel_path, e.rule_id, e.kind) for e in result.excluded] == [
        ("docs", "user.docs/**", "user"), ("notes.BAK", "user.*.bak", "user"),
        ("teszt", "user.teszt", "user")]


def test_paths_beyond_260_characters_are_scanned_and_bundled(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {LONG_PATH_FILE: "print('deep')\n"})
    assert len(os.path.join(root, *LONG_PATH_FILE.split("/"))) > 260
    result, _ = _scan(root)
    assert _paths(result) == [LONG_PATH_FILE]
    [md] = core.write_markdown("proj", result.included, str(tmp_path), root=str(root)).paths
    assert "print('deep')" in Path(md).read_text(encoding="utf-8")


def test_every_exclusion_is_logged_and_a_secret_folder_once(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {
        "main.py": "x = 1\n", "empty.txt": "", "node_modules/a.js": "x\n",
        "secrets/a.txt": "x\n", "secrets/b.txt": "x\n", "secrets/sub/c.txt": "x\n",
    })
    result, log = _scan(root)
    assert [line for line in log if line.startswith("skipped ")] == [
        "skipped empty.txt — empty file [size.empty]",
        "skipped node_modules — dependency, build or cache folder [junk_dir.node_modules]",
        "skipped secrets (3 files) — inside a folder that holds secrets "
        "[secret.secret_folder]",
    ]
    assert result.stats == {"included": 1, "bytes": 6, "excluded": 5,
                            "excluded_by_kind": {"junk_dir": 1, "secret": 3, "size": 1}}


def test_the_bundle_judges_a_file_by_where_it_really_lies(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {"main.py": "x = 1\n", "secrets/notes.txt": "out\n"})
    outside = make_project(tmp_path / "elsewhere", {"other.py": "y = 2\n"})
    entries = [core.FileEntry(str(root / "main.py"), "main.py", 6),
               core.FileEntry(str(root / "secrets" / "notes.txt"), "notes.txt", 4),  # a fake name
               core.FileEntry(str(outside / "other.py"), "other.py", 6)]
    log = []
    [md] = core.write_markdown("proj", entries, str(tmp_path), log=log.append,
                               root=str(root)).paths
    text = Path(md).read_text(encoding="utf-8")
    assert re.findall(r"^## FILE: (.*)$", text, flags=re.MULTILINE) == ["main.py"]
    assert [line for line in log if "notes.txt" in line and "[secret.secret_folder]" in line]
    assert [line for line in log if "other.py" in line and "[link.outside_project]" in line]


def test_the_window_warns_when_the_output_folder_is_inside_the_project(
    qtbot, make_project, tmp_path, monkeypatch
):
    from codepacker.ui.main_window import MainWindow

    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: shown.append(a)))
    root = make_project(tmp_path / "proj", {"main.py": "x = 1\n", "out/old.md": "# old\n"})
    window = MainWindow()
    qtbot.addWidget(window)
    window.project_edit.setText(str(root) + "/")
    window.output_edit.setText(str(root / "out"))
    window.start_scan()
    qtbot.waitUntil(window.scan_button.isEnabled, timeout=10_000)
    assert "the output folder is inside the project" in window.log_view.toPlainText()
    assert [entry.relative_path for entry in window.entries] == ["main.py"]
    assert shown == []

"""Characterization tests: lock the current scanner and bundle behaviour before the refactor."""

import base64
import io
import os
import zipfile
from pathlib import Path

import pytest

from codepacker import core
from fixtures import JUNK_FILES, SOURCE_FILES, TOKEN_FILES, hostile_tree, long_path_safe

PROJECT_NAME = "demo_project"


@pytest.fixture(scope="module")
def hostile_scan(tmp_path_factory):
    """Scan the hostile tree once with the GUI defaults (300 kB limit, no extra patterns).

    The tree is built without junctions (tests/test_scan_safety.py covers them).
    Returns (root, the included files): since spec S-1/T-1 the scan result also carries the
    exclusions, which tests/test_secrets.py checks.
    """
    root = hostile_tree(tmp_path_factory.mktemp("smoke") / "project", junctions=False)
    return root, core.scan_project(str(root), 300, "").included


def test_scanning_the_hostile_tree_returns_a_sorted_list_of_files(hostile_scan):
    root, entries = hostile_scan
    assert isinstance(entries, list)
    relative_paths = [entry.relative_path for entry in entries]
    assert relative_paths == sorted(relative_paths)
    assert set(SOURCE_FILES) <= set(relative_paths)
    for entry in entries:
        assert entry.full_path == os.path.join(root, *entry.relative_path.split("/"))
        assert entry.size == os.path.getsize(long_path_safe(entry.full_path)) > 0


def test_scan_skips_git_and_node_modules(hostile_scan):
    root, entries = hostile_scan
    assert all((root / junk).is_file() for junk in JUNK_FILES)
    relative_paths = [entry.relative_path for entry in entries]
    assert relative_paths  # an empty scan would make the next check pass vacuously
    assert [path for path in relative_paths if path.startswith((".git/", "node_modules/"))] == []


def test_md_bundle_starts_with_the_project_header_and_file_tree(hostile_scan, tmp_path):
    _, entries = hostile_scan
    paths = core.write_markdown(PROJECT_NAME, entries, str(tmp_path)).paths
    assert paths == [os.path.join(tmp_path, f"{PROJECT_NAME}_combined.md")]
    text = Path(paths[0]).read_text(encoding="utf-8")
    assert text.startswith(f"# PROJECT: {PROJECT_NAME}\n\nGenerated: ")
    assert f"\nFile count: {len(entries)}\n" in text
    file_tree = "".join(entry.relative_path + "\n" for entry in entries)
    assert f"\n## File structure\n\n```\n{file_tree}```\n\n---\n\n" in text
    for entry in entries:
        assert f"\n## FILE: {entry.relative_path}\n" in text


def test_base64_bundle_round_trips_for_an_ascii_project_name(hostile_scan, tmp_path):
    _, entries = hostile_scan
    [txt_path] = core.write_base64_zip(PROJECT_NAME, entries, str(tmp_path)).paths
    assert txt_path == os.path.join(tmp_path, f"{PROJECT_NAME}_zip.b64.txt")
    assert sorted(os.listdir(tmp_path)) == [f"{PROJECT_NAME}_zip.b64.txt"]  # temp zip removed

    lines = Path(txt_path).read_text(encoding="ascii").splitlines()
    assert lines[0] == "# THIS IS A BASE64-ENCODED ZIP FILE"
    payload = "".join(line for line in lines if not line.startswith("#"))
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload, validate=True))) as archive:
        assert archive.namelist() == [f"{PROJECT_NAME}/{entry.relative_path}" for entry in entries]
        for entry in entries:
            if entry.relative_path in TOKEN_FILES:
                continue  # its tokens are redacted (spec S-2), tests/test_secrets.py checks it
            original = Path(long_path_safe(entry.full_path)).read_bytes()
            assert archive.read(f"{PROJECT_NAME}/{entry.relative_path}") == original


def test_base64_header_explains_how_to_decode_and_unzip_it(hostile_scan, tmp_path):
    _, entries = hostile_scan
    [txt_path] = core.write_base64_zip(PROJECT_NAME, entries, str(tmp_path)).paths
    header = [line for line in Path(txt_path).read_text(encoding="ascii").splitlines()
              if line.startswith("#")]
    assert "# decode and unzip in your sandbox:" in header
    assert "#   unzip p.zip" in header

"""Self-tests of the test harness: settings isolation and the fixture generators."""

import codecs
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

import pytest

import conftest
from codepacker import settings
from fixtures import (
    CP1250_FILE,
    EMPTY_FILE,
    LINK_OUTSIDE,
    LONG_PATH_FILE,
    LOOP_TO_ROOT,
    OUTSIDE_FILES,
    OVERSIZED_FILE,
    UTF16_FILE,
    UTF8_BOM_FILE,
    big_tree,
    hostile_files,
    hostile_tree,
    long_path_safe,
    only,
)

# The paths the Task 1 brief requires in the hostile tree (spec section 4.2, S-1 and S-2).
REQUIRED_PATHS = {
    ".env", ".env.local", ".env.production", "my.env", "prod.env", "env.txt", "secret.yaml",
    "secret.yml", "secret_notes.md", "secrets.json", "credentials.json", "gcp-credentials.json",
    "token.json", "id_rsa", "id_rsa.bak", "id_rsa.pub", "AuthKey_ABC123.p8", "terraform.tfstate",
    ".docker/config.json", "appsettings.Production.json", ".npmrc", ".pypirc", "server.pem",
    "cert.pfx", "key.p12", "sub/dir/private.key", "disguised_pem.txt", "private_key_renamed.cfg",
    "aws.txt", "src/config.py", "node_modules/x/index.js", ".git/HEAD", "árvíztűrő tükörfúrógép.md",
}
PEM_HEADER = re.compile(rb"-{5}BEGIN (RSA )?PRIVATE KEY-{5}")


def _read(root, relative):
    with open(long_path_safe(Path(root).joinpath(*relative.split("/"))), "rb") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def hostile_root(tmp_path_factory):
    return hostile_tree(tmp_path_factory.mktemp("harness") / "project", junctions=False)


def test_each_test_gets_a_fresh_settings_file_in_the_pytest_temp_folder(
    isolated_settings, tmp_path_factory
):
    assert settings.settings_file() == str(isolated_settings)
    assert isolated_settings.is_relative_to(tmp_path_factory.getbasetemp())
    assert not isolated_settings.parent.exists()  # nothing left over; the app creates it on save


def test_without_the_per_test_redirect_the_settings_still_go_to_a_temp_folder(monkeypatch):
    # the fail-safe conftest sets at import time, for anything that runs outside a test
    monkeypatch.undo()  # drops the per-test redirect (isolated_settings uses this monkeypatch)
    session_file = os.path.join(conftest.SESSION_FOLDER, "CodePacker", "settings.ini")
    assert settings.settings_file_override == session_file  # the first layer
    assert settings.default_settings_file() == session_file  # %APPDATA%, the second one
    assert settings.settings_file() == session_file
    temp = Path(tempfile.gettempdir()).resolve()
    assert Path(conftest.SESSION_FOLDER).resolve().is_relative_to(temp)


def test_only_returns_the_single_widget_or_names_what_is_missing():
    assert only(["the widget"], "button 'Scan'") == "the widget"
    with pytest.raises(LookupError, match="expected one button 'Scan' in the window, found 0"):
        only([], "button 'Scan'")
    with pytest.raises(LookupError, match="found 2"):
        only(["one", "two"], "button 'Scan'")


def test_make_project_writes_exact_bytes_and_stays_inside_the_root(make_project, tmp_path):
    root = make_project(tmp_path / "demo", {"a.txt": "one\ntwo\n", "sub/b.bin": b"\x00\xff"})
    assert root == tmp_path / "demo"
    assert (root / "a.txt").read_bytes() == b"one\ntwo\n"
    assert (root / "sub" / "b.bin").read_bytes() == b"\x00\xff"
    for escaping in ("../outside.txt", "/absolute.txt", "C:/drive.txt", "back\\slash.txt"):
        with pytest.raises(ValueError):
            make_project(root, {escaping: "x"})


def test_make_project_creates_the_root_for_an_empty_spec(make_project, tmp_path):
    root = make_project(tmp_path / "empty", {})
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_make_project_validates_every_key_before_writing_anything(make_project, tmp_path):
    with pytest.raises(ValueError):
        make_project(tmp_path / "demo", {"fine.txt": "x", "../escape.txt": "y"})
    assert not (tmp_path / "demo").exists()


def test_hostile_tree_writes_every_file_of_the_matrix(hostile_root):
    files = hostile_files()
    assert REQUIRED_PATHS <= set(files)
    assert "config/.ENV" in files  # the upper-case variant lives in its own folder
    assert len({path.lower() for path in files}) == len(files)  # no name clashes on Windows
    assert {".py", ".js", ".tsx", ".go", ".rs"} <= {PurePosixPath(path).suffix for path in files}
    for relative, content in files.items():
        expected = content.encode("utf-8") if isinstance(content, str) else content
        assert _read(hostile_root, relative) == expected, relative
    assert not os.path.lexists(hostile_root / LINK_OUTSIDE)  # junctions=False creates none


def test_hostile_tree_edge_cases_match_the_brief(hostile_root):
    assert len(os.path.join(hostile_root, *LONG_PATH_FILE.split("/"))) > 260
    assert len(_read(hostile_root, OVERSIZED_FILE)) == 350 * 1024
    assert _read(hostile_root, EMPTY_FILE) == b""

    cp1250 = _read(hostile_root, CP1250_FILE)
    assert CP1250_FILE.endswith(".txt") and "tükörfúrógép" in cp1250.decode("cp1250")
    with pytest.raises(UnicodeDecodeError):
        cp1250.decode("utf-8")
    assert UTF16_FILE.endswith(".ps1")
    assert _read(hostile_root, UTF16_FILE).startswith(codecs.BOM_UTF16_LE)
    assert UTF8_BOM_FILE.endswith(".cs")
    assert _read(hostile_root, UTF8_BOM_FILE).startswith(codecs.BOM_UTF8)

    assert PEM_HEADER.search(_read(hostile_root, "disguised_pem.txt")).group(1) == b"RSA "
    assert PEM_HEADER.search(_read(hostile_root, "private_key_renamed.cfg")).group(1) is None
    assert b"AKIA" + b"IOSFODNN7EXAMPLE" in _read(hostile_root, "aws.txt")
    config = _read(hostile_root, "src/config.py").decode("utf-8")
    assert 'OPENAI_API_KEY = "sk-' + "a" * 48 + '"' in config
    assert 'GITHUB_TOKEN = "ghp_' + "a" * 36 + '"' in config


@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions exist only on Windows")
def test_hostile_tree_junctions_point_outside_and_back_to_the_root(tmp_path):
    root = hostile_tree(tmp_path / "project")
    link_outside = root / LINK_OUTSIDE
    loop = root.joinpath(*LOOP_TO_ROOT.split("/"))
    if not (os.path.isjunction(link_outside) and os.path.isjunction(loop)):
        pytest.skip("mklink /J is not available on this machine")
    real_root = os.path.realpath(root)
    assert os.path.realpath(loop) == real_root
    assert not os.path.realpath(link_outside).startswith(real_root + os.sep)
    assert sorted(os.listdir(link_outside)) == sorted(OUTSIDE_FILES)


def test_hostile_tree_without_mklink_still_builds_the_files(tmp_path, monkeypatch):
    def mklink_unavailable(*args, **kwargs):
        raise FileNotFoundError("cmd")

    monkeypatch.setattr("fixtures.subprocess.run", mklink_unavailable)
    root = hostile_tree(tmp_path / "project")
    assert not os.path.lexists(root / LINK_OUTSIDE)
    assert _read(root, "id_rsa.pub") == hostile_files()["id_rsa.pub"].encode("utf-8")


def test_big_tree_spreads_small_files_over_60_folders(tmp_path):
    root = big_tree(tmp_path / "big", n=180)
    files = [path for path in root.rglob("*") if path.is_file()]
    assert len(files) == 180
    assert len({path.parent for path in files}) == 60
    assert all(path.suffix == ".py" and path.stat().st_size < 1024 for path in files)

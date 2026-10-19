"""Secret filtering end to end on the hostile matrix (spec S-1, S-2, T-1, T-2)."""

import base64
import codecs
import io
import re
import zipfile
from pathlib import Path

import pytest

from codepacker import core
from fixtures import (
    EMPTY_FILE,
    FAKE_PRIVATE_KEY,
    FAKE_RSA_PRIVATE_KEY,
    JUNK_FILES,
    OVERSIZED_FILE,
    PRIVATE_KEY_CONTENT_FILES,
    PRIVATE_KEY_CONTENT_RULE,
    PUBLIC_KEY_FILES,
    SECRET_NAME_FILES,
    SECRET_RULE_BY_FILE,
    SOURCE_FILES,
    TOKEN_FILES,
    TOKEN_TYPES,
    TOKENS_BY_FILE,
    hostile_tree,
    long_path_safe,
)

PROJECT_NAME = "hostile"

# Text that must never reach a bundle or a log: every fake token and private-key line.
NEVER_SHOWN = sorted(
    {*TOKEN_TYPES, *FAKE_PRIVATE_KEY.splitlines(), *FAKE_RSA_PRIVATE_KEY.splitlines()})


@pytest.fixture(scope="module")
def scanned(tmp_path_factory):
    """Scan the hostile tree once with the GUI defaults; return (scan result, log lines).

    The tree has no junctions (tests/test_scan_safety.py covers them).
    """
    root = hostile_tree(tmp_path_factory.mktemp("secrets") / "project", junctions=False)
    log = []
    result = core.scan_project(str(root), 300, "", log=log.append)
    return result, log


@pytest.fixture(scope="module")
def packed(scanned, tmp_path_factory):
    """Build both outputs from the included files; return (MD text, {relative path: zip bytes})."""
    result, _ = scanned
    output = tmp_path_factory.mktemp("secrets_output")
    [md_path] = core.write_markdown(PROJECT_NAME, result.included, str(output)).paths
    [b64_path] = core.write_base64_zip(PROJECT_NAME, result.included, str(output)).paths
    return Path(md_path).read_text(encoding="utf-8"), _unzip(b64_path)


def _unzip(b64_path):
    lines = Path(b64_path).read_text(encoding="ascii").splitlines()
    payload = "".join(line for line in lines if not line.startswith("#"))
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload, validate=True))) as archive:
        return {name.split("/", 1)[1]: archive.read(name) for name in archive.namelist()}


def _included(result):
    return {entry.relative_path for entry in result.included}


def _exclusion(result, path):
    found = [exclusion for exclusion in result.excluded if exclusion.rel_path == path]
    assert len(found) == 1, f"expected one exclusion for {path}, found {found}"
    return found[0]


def _names(path, line):
    """Whether ``line`` mentions ``path`` as a whole path (".env" is not in ".env.local")."""
    return re.search(rf"(?<![\w./-]){re.escape(path)}(?![\w./-])", line) is not None


def _lines(content):
    """The lines of a fixture file's content that are long enough to recognize in a log."""
    text = content.decode("latin-1") if isinstance(content, bytes) else content
    return [line for line in text.splitlines() if len(line.strip()) >= 8]


def _redacted(path):
    """The token fixture ``path`` the way it must appear in a bundle."""
    text = TOKEN_FILES[path]
    for token in TOKENS_BY_FILE[path]:
        text = text.replace(token, f"[REDACTED:{TOKEN_TYPES[token]}]")
    return text


def _token_lines(path):
    """[(type, line number)] of the tokens in the token fixture ``path``, in file order."""
    return [(TOKEN_TYPES[token], number)
            for number, line in enumerate(TOKEN_FILES[path].splitlines(), 1)
            for token in TOKENS_BY_FILE[path] if token in line]


# ------------------------------------------------------------------------------------------------
# Excluded by name (spec S-1)
# ------------------------------------------------------------------------------------------------


def test_secret_named_files_are_excluded_by_their_rule(scanned):
    result, _ = scanned
    for path in SECRET_NAME_FILES:
        assert path not in _included(result)
        exclusion = _exclusion(result, path)
        assert (exclusion.rule_id, exclusion.kind) == (SECRET_RULE_BY_FILE[path], "secret")
        assert exclusion.reason != ""


def test_sources_and_the_public_key_are_included_untouched(scanned):
    result, _ = scanned
    for path in {*SOURCE_FILES, *PUBLIC_KEY_FILES}:
        assert path in _included(result)
        assert [e for e in result.excluded if e.rel_path == path] == []
        assert [r for r in result.redactions if r.rel_path == path] == []


def test_size_exclusions_and_junk_folders_are_recorded_with_their_rule(scanned):
    result, _ = scanned
    for path, rule_id in [(EMPTY_FILE, "size.empty"), (OVERSIZED_FILE, "size.too_large")]:
        assert path not in _included(result)
        assert (_exclusion(result, path).rule_id, _exclusion(result, path).kind) == (
            rule_id, "size")
    for path in JUNK_FILES:  # a junk folder is one exclusion, its files are not even listed
        folder = path.split("/")[0]
        assert _exclusion(result, folder).kind == "junk_dir"
        assert [e for e in result.excluded if e.rel_path.startswith(folder + "/")] == []


def test_secret_folders_are_excluded_file_by_file_and_source_files_by_content_only(
    make_project, tmp_path
):
    # rulings R1 and R2: a folder that holds secrets keeps every file out, whatever its name;
    # a source file is never excluded for its name, the content scanner guards it instead
    root = make_project(tmp_path / "project", {
        "secrets/api_key.txt": "kept out by its folder\n",
        "k8s/secrets/db.yaml": "user: app\n",
        "credentials/__init__.py": "from .store import load\n",
        "src/secret_scan.py": "print('scanning')\n",
        "migrations/env.py": "config = context.config\n",
        "secret_notes.md": "a data file named secret\n",
    })
    result = core.scan_project(str(root), 300, "")
    assert _included(result) == {"src/secret_scan.py", "migrations/env.py"}
    assert {(e.rel_path, e.rule_id) for e in result.excluded} == {
        ("secrets/api_key.txt", "secret.secret_folder"),
        ("k8s/secrets/db.yaml", "secret.secret_folder"),
        ("credentials/__init__.py", "secret.secret_folder"),
        ("secret_notes.md", "secret.secret_in_name"),
    }


def test_secret_exclusions_are_logged_by_name_and_rule_but_never_by_content(scanned):
    _, log = scanned
    for path, rule_id in SECRET_RULE_BY_FILE.items():
        assert [line for line in log if _names(path, line) and f"[{rule_id}]" in line], path
    leaked = [line for line in log
              for content in SECRET_NAME_FILES.values() for secret in _lines(content)
              if secret in line]
    assert leaked == []


# ------------------------------------------------------------------------------------------------
# Found by content (spec S-2)
# ------------------------------------------------------------------------------------------------


def test_files_holding_a_private_key_are_excluded_whatever_their_name(scanned):
    result, log = scanned
    for path in PRIVATE_KEY_CONTENT_FILES:
        assert path not in _included(result)
        exclusion = _exclusion(result, path)
        assert (exclusion.rule_id, exclusion.kind, exclusion.reason) == (
            PRIVATE_KEY_CONTENT_RULE, "secret", "private key material")
        assert [line for line in log
                if _names(path, line) and f"[{PRIVATE_KEY_CONTENT_RULE}]" in line]


def test_token_files_are_included_and_each_token_is_logged_by_type_and_line(scanned):
    result, log = scanned
    for path in TOKEN_FILES:
        assert path in _included(result)
        found = [(r.token_type, r.line) for r in result.redactions if r.rel_path == path]
        assert found == _token_lines(path)
        for token_type, line in found:
            assert [entry for entry in log if _names(path, entry) and f"line {line}" in entry
                    and f"[{token_type}]" in entry]


def test_the_md_and_the_zip_hold_the_token_files_with_every_token_redacted(packed):
    md, files = packed
    for path in TOKEN_FILES:
        block = md.split(f"\n## FILE: {path}\n", 1)[1].split("\n## FILE: ", 1)[0]
        assert _redacted(path) in block
        assert files[path] == _redacted(path).encode("utf-8")


def test_the_zip_holds_every_other_included_file_unchanged(scanned, packed):
    result, _ = scanned
    _, files = packed
    assert sorted(files) == sorted(_included(result))
    for entry in result.included:
        if entry.relative_path not in TOKEN_FILES:
            assert files[entry.relative_path] == Path(long_path_safe(entry.full_path)).read_bytes()


def test_no_token_or_private_key_line_reaches_the_md_the_zip_or_the_log(scanned, packed):
    _, log = scanned
    md, files = packed
    outputs = [md, *(data.decode("utf-8", "replace") for data in files.values()), *log]
    assert [secret for secret in NEVER_SHOWN for text in outputs if secret in text] == []


def test_the_scan_sums_up_the_secret_files_and_the_redacted_tokens(scanned):
    result, log = scanned
    files = len(SECRET_NAME_FILES) + len(PRIVATE_KEY_CONTENT_FILES)
    tokens = sum(len(found) for found in TOKENS_BY_FILE.values())
    summary = result.secret_summary
    assert (summary.files_excluded, summary.tokens_redacted) == (files, tokens)
    assert f"secrets: {files} file(s) excluded, {tokens} token(s) redacted" in log


# ------------------------------------------------------------------------------------------------
# Hard exclusion: the bundle refuses secret files even when they are passed to it
# ------------------------------------------------------------------------------------------------

# A caller that bypassed the scanner passes one ordinary file and one of these:
# (the relative path it passes, the file on disk, the rule that must refuse it).
# Every path form Windows accepts and a misleading relative path are covered (review I2), and
# so is a private key that can't be read as UTF-8 text (review M7).
REFUSAL_CASES = [
    (".env", ".env", "secret.dotenv"),
    ("keys/id_rsa", "keys/id_rsa", "secret.ssh_key"),
    ("notes/disguised_pem.txt", "notes/disguised_pem.txt", PRIVATE_KEY_CONTENT_RULE),
    ("secrets/notes.md", "secrets/notes.md", "secret.secret_folder"),
    ("sub\\.npmrc", "sub/.npmrc", "secret.login_config"),
    ("keys\\id_rsa", "keys/id_rsa", "secret.ssh_key"),
    (".docker\\config.json", ".docker/config.json", "secret.docker_config"),
    ("secret.yaml.", "secret.yaml", "secret.secret_in_name"),
    (".npmrc ", ".npmrc", "secret.login_config"),
    ("ſecret.yaml", "secret.yaml", "secret.secret_in_name"),
    ("npm-settings.txt", ".npmrc", "secret.login_config"),  # only the file on disk tells
    ("notes/key_utf16.txt", "notes/key_utf16.txt", PRIVATE_KEY_CONTENT_RULE),
]
FILES_ON_DISK = {
    ".env": SECRET_NAME_FILES[".env"],
    "keys/id_rsa": FAKE_RSA_PRIVATE_KEY,
    "notes/disguised_pem.txt": PRIVATE_KEY_CONTENT_FILES["disguised_pem.txt"],
    "secrets/notes.md": "a note kept with the secrets\n",
    "sub/.npmrc": SECRET_NAME_FILES[".npmrc"],
    ".docker/config.json": SECRET_NAME_FILES[".docker/config.json"],
    "secret.yaml": SECRET_NAME_FILES["secret.yaml"],
    ".npmrc": SECRET_NAME_FILES[".npmrc"],
    "notes/key_utf16.txt": codecs.BOM_UTF16_LE + FAKE_PRIVATE_KEY.encode("utf-16-le"),
}


def _entry(root, on_disk, passed_as):
    """A FileEntry built by hand, the way any caller could: ``passed_as`` names ``on_disk``."""
    full_path = root.joinpath(*on_disk.split("/"))
    return core.FileEntry(str(full_path), passed_as, full_path.stat().st_size)


def test_the_bundle_refuses_secret_files_passed_to_it(make_project, tmp_path):
    for number, (passed_as, on_disk, rule_id) in enumerate(REFUSAL_CASES):
        root = make_project(tmp_path / f"project{number}",
                            {"main.py": "print('hello')\n", on_disk: FILES_ON_DISK[on_disk]})
        entries = [_entry(root, "main.py", "main.py"), _entry(root, on_disk, passed_as)]
        output = tmp_path / f"output{number}"
        output.mkdir()
        log = []
        [md_path] = core.write_markdown("project", entries, str(output), log=log.append).paths
        md = Path(md_path).read_text(encoding="utf-8")
        assert "\nFile count: 1\n" in md, passed_as
        assert re.findall(r"^## FILE: (.*)$", md, flags=re.MULTILINE) == ["main.py"]
        [b64_path] = core.write_base64_zip("project", entries, str(output),
                                           log=log.append).paths
        assert "# file count: 1" in Path(b64_path).read_text(encoding="utf-8").splitlines()
        files = _unzip(b64_path)
        assert sorted(files) == ["main.py"], passed_as
        packed = md + files["main.py"].decode("utf-8")
        assert [secret for secret in NEVER_SHOWN if secret in packed] == []

        # the refusal is logged by name and rule (once per output), without anything from the file
        assert len([line for line in log if passed_as in line and f"[{rule_id}]" in line]) == 2
        content = FILES_ON_DISK[on_disk]
        assert [line for line in log for secret in _lines(content) if secret in line] == []

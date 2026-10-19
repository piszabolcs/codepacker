"""Ad-hoc packages, Copy as Markdown, the token estimate and the command line (spec 6.3, T-22, T-23)."""

import datetime
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QGuiApplication

from codepacker import __main__ as cli
from codepacker import core
from codepacker.core import bundle
from codepacker.ui.main_window import MainWindow
from fixtures import FAKE_RSA_PRIVATE_KEY
from gui_helpers import listed_paths

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT = {
    "main.py": "print('hello')\n",
    "src/app.js": "export const a = 1;\n",
    "src/util/helpers.py": "def add(a, b):\n    return a + b\n",
    "src/.env": "API_TOKEN=fake-local-token\n",
    "docs/guide.md": "# Guide\n",
    "img/logo.png": "not really a png\n",
}


class FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 12, 9, 30)


@pytest.fixture
def window(qtbot):
    main_window = MainWindow()
    qtbot.addWidget(main_window)
    return main_window


def _drop(window, qtbot, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    window.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    qtbot.waitUntil(lambda: not window.busy, timeout=10_000)


def test_an_ad_hoc_selection_keeps_paths_relative_to_the_common_parent(make_project, tmp_path):
    root = make_project(tmp_path / "proj", PROJECT)
    chosen = [root / "src" / "util" / "helpers.py", root / "src" / ".env",
              root / "img" / "logo.png", root / "docs"]
    result = core.scan_selection([str(path) for path in chosen], 300, "")
    assert result.root == str(root)
    assert [entry.relative_path for entry in result.included] == [
        "docs/guide.md", "src/util/helpers.py"]
    assert [(e.rel_path, e.kind) for e in result.excluded] == [
        ("img/logo.png", "binary"), ("src/.env", "secret")]

    # a file chosen from inside a folder that holds secrets stays out, even on its own
    secrets = make_project(tmp_path / "secrets", {"notes.txt": "x\n", "key.txt": "y\n"})
    alone = core.scan_selection([str(secrets / "notes.txt")], 300, "")
    assert alone.included == [] and alone.excluded[0].kind == "secret"


def test_dropping_files_makes_an_ad_hoc_package(window, qtbot, make_project, tmp_path,
                                                message_boxes):
    root = make_project(tmp_path / "proj", PROJECT)
    _drop(window, qtbot, [root / "main.py", root / "src" / "app.js", root / "src" / ".env"])
    assert listed_paths(window) == ["main.py", "src/app.js"]
    assert window.scanned_root == str(root)
    assert window.findChildren(type(window.browse_button), "") and \
        window.browse_files_button.text() == "Browse files…"
    window.start_pack()
    qtbot.waitUntil(lambda: not window.busy, timeout=10_000)
    md = (tmp_path / "proj_codepacker" / "proj_combined.md").read_text(encoding="utf-8")
    assert "## FILE: src/app.js" in md and "## FILE: src/util" not in md


def test_copy_as_markdown_fills_the_clipboard_and_shows_the_token_estimate(
    window, qtbot, make_project, tmp_path, message_boxes
):
    root = make_project(tmp_path / "proj", PROJECT)
    _drop(window, qtbot, [root])
    selected = window.selected_entries()
    md_estimate, _ = core.estimate_sizes(selected, "proj")
    assert window.size_label.text() == "MD ~{} · ~{} tokens".format(
        core.format_size(md_estimate), md_estimate // 4)

    window.copy_as_markdown()
    expected, _ = core.markdown_text("proj", selected, root=str(root))
    assert QGuiApplication.clipboard().text() == expected
    assert expected.startswith("# PROJECT: proj\n") and "## FILE: src/util/helpers.py" in expected
    assert message_boxes == []


def test_copy_as_markdown_refuses_more_than_200_kb(window, qtbot, make_project, tmp_path,
                                                   message_boxes):
    root = make_project(tmp_path / "big", {f"data_{i}.txt": "x" * 60_000 + "\n" for i in range(4)})
    _drop(window, qtbot, [root])
    QGuiApplication.clipboard().setText("before")
    window.copy_as_markdown()
    assert QGuiApplication.clipboard().text() == "before"
    [(kind, (_, text))] = message_boxes
    assert kind == "information" and "Build a file package instead" in text


def test_the_command_line_sizes_and_exit_codes(make_project, tmp_path, capsys, monkeypatch):
    assert [cli.parse_size(text) for text in ("500k", "2M", "750kb", "1000")] == [
        512_000, 2_097_152, 768_000, 1000]
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["x", "--max-part", "lots"])

    root = make_project(tmp_path / "proj", PROJECT)
    out = tmp_path / "out"
    assert cli.main([str(root), "--md", "--b64", "--out", str(out), "--quiet"]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert [line for line in printed if not line.startswith("written: ")] == [
        "md: ok", "b64: ok"]
    assert sorted(path.name for path in out.iterdir()) == ["proj_combined.md",
                                                          "proj_zip.b64.txt"]

    assert cli.main([str(tmp_path / "missing")]) == 1

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(bundle, "write_base64_zip", disk_full)
    assert cli.main([str(root), "--b64", "--out", str(out)]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "b64: FAILED disk full"


def test_the_command_line_writes_the_same_md_as_the_window(
    window, qtbot, make_project, tmp_path, message_boxes, monkeypatch
):
    monkeypatch.setattr(bundle.datetime, "datetime", FixedDateTime)
    root = make_project(tmp_path / "proj", {**PROJECT, "keys/id_rsa": FAKE_RSA_PRIVATE_KEY})
    window.output_edit.setText(str(tmp_path / "gui"))
    _drop(window, qtbot, [root])
    window.start_pack()
    qtbot.waitUntil(lambda: not window.busy, timeout=10_000)
    assert cli.main([str(root), "--md", "--out", str(tmp_path / "cli")]) == 0
    gui = (tmp_path / "gui" / "proj_combined.md").read_bytes()
    assert (tmp_path / "cli" / "proj_combined.md").read_bytes() == gui


def test_the_command_line_runs_without_pyside6(make_project, tmp_path):
    root = make_project(tmp_path / "proj", PROJECT)
    code = ("import sys; sys.modules['PySide6'] = None; from codepacker.__main__ import main; "
            "sys.exit(main(sys.argv[1:]))")
    result = subprocess.run([sys.executable, "-c", code, str(root), "--out", str(tmp_path / "x")],
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                            check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "md: ok"
    assert (tmp_path / "x" / "proj_combined.md").is_file()

"""GUI state (spec C-3, C-4, C-10, C-11, C-12, G-6): selection model, filter, results, busy/cancel."""

import os
import re
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from codepacker import core
from codepacker.core import bundle, scanner
from codepacker.settings import Settings
from codepacker.ui.main_window import MainWindow
from gui_helpers import checked_paths, listed_paths

FILES = {"a.py": "a = 1\n", "b.py": "b = 2\n", "src/c.py": "c = 3\n", "src/d.js": "d = 4;\n",
         "e.md": "# e\n"}


@pytest.fixture
def window(qtbot):
    main_window = MainWindow()
    qtbot.addWidget(main_window)
    return main_window


def _scan(window, qtbot, root):
    window.project_edit.setText(str(root))
    window.start_scan()
    qtbot.waitUntil(lambda: not window.busy, timeout=10_000)


def _build(window, qtbot):
    window.start_pack()
    qtbot.waitUntil(lambda: not window.busy, timeout=10_000)


def _filter(window, text):
    window.filter_edit.setText(text)
    window.apply_filter()  # what the debounce timer does 150 ms later


def _packed_files(md_path):
    return sorted(re.findall(r"^## FILE: (.*)$", md_path.read_text(encoding="utf-8"),
                             re.MULTILINE))


def _slow(monkeypatch, module, name, seconds=0.05):
    real = getattr(module, name)

    def slow(*args, **kwargs):
        time.sleep(seconds)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, slow)


def test_the_package_holds_exactly_the_checked_files_whatever_the_filter(
    window, qtbot, make_project, tmp_path, message_boxes
):
    root = make_project(tmp_path / "proj", FILES)
    md = tmp_path / "proj_codepacker" / "proj_combined.md"
    _scan(window, qtbot, root)

    _filter(window, ".py")
    window.select_none()  # only the rows the filter shows
    _filter(window, "")
    assert checked_paths(window) == ["e.md", "src/d.js"]
    _build(window, qtbot)
    assert _packed_files(md) == checked_paths(window)

    window.select_none()
    _filter(window, ".py")
    window.select_all()
    _filter(window, "")
    assert checked_paths(window) == ["a.py", "b.py", "src/c.py"]
    _build(window, qtbot)
    assert _packed_files(md) == checked_paths(window)


def test_the_filter_waits_until_the_typing_stops(window, qtbot, make_project, tmp_path,
                                                 monkeypatch):
    _scan(window, qtbot, make_project(tmp_path / "proj", FILES))
    applied = []
    real = window.file_model.set_filter
    monkeypatch.setattr(window.file_model, "set_filter", lambda q: applied.append(q) or real(q))
    for text in ("s", "sr", "src"):
        window.filter_edit.setText(text)
    assert applied == [] and len(listed_paths(window)) == 5
    qtbot.waitUntil(lambda: applied == ["src"], timeout=2_000)
    assert listed_paths(window) == ["src/c.py", "src/d.js"]


def test_bulk_toggles_stay_fast_on_6000_files(window):
    window.entries = [core.FileEntry(f"C:/demo/pkg{index // 1000}/m_{index:05d}.py",
                                     f"pkg{index // 1000}/m_{index:05d}.py", 100)
                      for index in range(6000)]
    window.fill_tree()
    model = window.file_model
    folder = model.index(0, 0)
    assert model.rowCount(folder) == 1000

    start = time.perf_counter()
    model.setData(folder, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert time.perf_counter() - start < 0.5
    assert len(window.selected_entries()) == 5000
    for toggle in (window.select_none, window.select_all):
        start = time.perf_counter()
        toggle()
        assert time.perf_counter() - start < 0.5
    assert len(window.selected_entries()) == 6000


def test_the_result_dialog_says_finished_or_finished_with_errors(
    window, qtbot, make_project, tmp_path, message_boxes, monkeypatch
):
    _scan(window, qtbot, make_project(tmp_path / "proj", FILES))
    window.b64_checkbox.setChecked(True)
    _build(window, qtbot)
    kind, (_, text) = message_boxes[-1]
    assert kind == "information" and text.startswith("Finished:\n\nmd: ok\nb64: ok\n")
    assert window.progress_bar.value() == 100

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(bundle, "write_base64_zip", disk_full)
    _build(window, qtbot)
    kind, (_, text) = message_boxes[-1]
    assert kind == "warning"
    assert text.startswith("Finished with errors:\n\nmd: ok\nb64: FAILED disk full\n")
    assert window.statusBar().currentMessage() == "finished with errors"
    assert window.progress_bar.value() < 100


def test_cancel_stops_the_build_quickly_and_deletes_its_output(
    window, qtbot, make_project, tmp_path, message_boxes, monkeypatch
):
    root = make_project(tmp_path / "proj", {f"m{index:02d}.py": "x = 1\n" for index in range(40)})
    _scan(window, qtbot, root)
    window.b64_checkbox.setChecked(True)
    _slow(monkeypatch, bundle, "bundle_bytes")  # the MD is quick, the zip takes 2 s
    md = tmp_path / "proj_codepacker" / "proj_combined.md"
    window.start_pack()
    qtbot.waitUntil(md.exists, timeout=5_000)

    # busy: no other folder, no new scan, and a drop is ignored
    assert not any(control.isEnabled() for control in (
        window.rescan_action, window.open_action, window.browse_button, window.recent_combo,
        window.scan_button, window.build_button))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path))])
    window.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert window.project_edit.text() == str(root)

    start = time.perf_counter()
    window.cancel_work()
    qtbot.waitUntil(lambda: not window.busy, timeout=5_000)
    assert time.perf_counter() - start < 1.0
    assert list((tmp_path / "proj_codepacker").iterdir()) == []
    assert message_boxes == []
    assert window.statusBar().currentMessage() == "cancelled, the partial output was deleted"


def test_an_interrupted_scan_shows_a_partial_list_and_cannot_be_built(
    window, qtbot, make_project, tmp_path, monkeypatch
):
    root = make_project(tmp_path / "proj", {f"m{index:02d}.py": "x = 1\n" for index in range(40)})
    _slow(monkeypatch, scanner, "check_file")
    window.project_edit.setText(str(root))
    window.start_scan()
    qtbot.wait(200)
    window.cancel_work()
    qtbot.waitUntil(lambda: not window.busy, timeout=5_000)
    assert window.statusBar().currentMessage() == "cancelled \u2013 partial list"
    assert 0 < len(window.entries) < 40
    assert not window.build_button.isEnabled()


def test_closing_the_window_while_busy_cancels_and_waits_for_the_worker(
    qtbot, make_project, tmp_path, message_boxes, monkeypatch
):
    root = make_project(tmp_path / "proj", {f"m{index:02d}.py": "x = 1\n" for index in range(40)})
    window = MainWindow()
    _scan(window, qtbot, root)
    _slow(monkeypatch, bundle, "bundle_text")
    window.start_pack()
    worker = window.pack_worker
    window.close()
    assert not worker.isRunning()
    assert not (tmp_path / "proj_codepacker" / "proj_combined.md").exists()
    window.deleteLater()


def test_recent_folders_are_checked_once_per_refresh_and_can_be_cleared(
    qtbot, tmp_path, isolated_settings, monkeypatch
):
    stored = Settings()
    for name in "abc":
        (tmp_path / name).mkdir()
        stored.add_recent_folder(str(tmp_path / name))
    stored.save()
    window = MainWindow()
    qtbot.addWidget(window)

    looked_at = []
    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir", lambda path: looked_at.append(path) or real_isdir(path))
    window.refresh_recent_folders()
    assert len(looked_at) == 3

    window.clear_recent_action.trigger()
    assert window.recent_combo.count() == 1
    assert Settings().recent_folders() == []


def test_the_window_creates_no_settings_folder_until_it_saves(qtbot, isolated_settings):
    window = MainWindow()
    qtbot.addWidget(window)
    assert not Path(isolated_settings).parent.exists()

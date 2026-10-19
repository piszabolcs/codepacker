"""Settings live in one INI file, %APPDATA%\\CodePacker\\settings.ini, never in the registry."""

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QComboBox

from codepacker import settings
from codepacker.settings import Settings
from codepacker.ui.main_window import MainWindow
from fixtures import only

# Every key the app could have written with its old or new names.
REGISTRY_KEYS = (r"Software\psz", r"Software\CodePacker", r"Software\PinterSzabolcs")


def _registry_snapshot():
    """{key path: sorted (name, data) values} for every existing key below REGISTRY_KEYS."""
    import winreg

    snapshot = {}

    def walk(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            return
        with key:
            subkey_count, value_count, _ = winreg.QueryInfoKey(key)
            snapshot[path] = sorted(winreg.EnumValue(key, i)[:2] for i in range(value_count))
            for name in [winreg.EnumKey(key, i) for i in range(subkey_count)]:
                walk(path + "\\" + name)

    for path in REGISTRY_KEYS:
        walk(path)
    return snapshot


def _recent_combo(window):
    return only(window.findChildren(QComboBox), "recent-folders dropdown")


def _recent_items(combo):
    return [combo.itemText(index) for index in range(1, combo.count())]  # item 0: placeholder


def test_the_default_settings_file_is_in_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    expected = os.path.join(str(tmp_path), "CodePacker", "settings.ini")
    assert settings.default_settings_file() == expected


def test_without_appdata_the_settings_go_to_the_per_user_config_folder(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    config = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    assert settings.default_settings_file() == os.path.join(config, "CodePacker", "settings.ini")


def test_settings_are_an_ini_file_at_the_settings_path(isolated_settings):
    stored = Settings()
    assert stored.path == str(isolated_settings)
    assert stored.store.format() == QSettings.Format.IniFormat
    assert Path(stored.store.fileName()) == isolated_settings


def test_the_settings_folder_is_created_on_the_first_save_not_on_startup(isolated_settings):
    stored = Settings()
    assert not isolated_settings.parent.exists()
    stored.write("md_enabled", False)
    stored.save()
    assert "md_enabled=false" in isolated_settings.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="the registry exists only on Windows")
def test_saving_settings_writes_nothing_to_the_registry(isolated_settings, tmp_path):
    before = _registry_snapshot()
    stored = Settings()
    stored.write("md_enabled", False)
    stored.add_recent_folder(str(tmp_path))
    stored.save()
    assert isolated_settings.is_file()
    assert _registry_snapshot() == before


def test_values_from_the_file_come_back_with_the_type_of_their_default(isolated_settings):
    # after a restart QSettings returns INI values as text; read() converts them back
    isolated_settings.parent.mkdir(parents=True)
    isolated_settings.write_text(
        "[General]\nmd_enabled=false\npart_count=3\nrecent_folders=C:/one\n", encoding="utf-8"
    )
    stored = Settings()
    assert stored.read("md_enabled", True) is False
    assert stored.read("part_count", 1) == 3
    assert stored.read("recent_folders", []) == ["C:/one"]
    assert stored.read("missing", "default") == "default"


def test_the_window_saves_its_settings_to_the_ini_file(qtbot, isolated_settings):
    window = MainWindow()
    qtbot.addWidget(window)
    window.close()  # closing saves the settings
    text = isolated_settings.read_text(encoding="utf-8")
    for key in ("md_enabled", "b64_enabled", "split_parts", "max_part_kb", "max_kb",
                "extra_excludes",
                "output_dir"):
        assert f"\n{key}=" in text


def test_recent_folders_leave_out_folders_that_no_longer_exist(tmp_path):
    kept, deleted = tmp_path / "kept", tmp_path / "deleted"
    kept.mkdir()
    deleted.mkdir()
    stored = Settings()
    stored.add_recent_folder(str(kept))
    stored.add_recent_folder(str(deleted))
    deleted.rmdir()
    assert stored.recent_folders() == [str(kept)]


def test_adding_a_recent_folder_drops_the_missing_ones_from_the_file(tmp_path):
    old, deleted, new = tmp_path / "old", tmp_path / "deleted", tmp_path / "new"
    for folder in (old, deleted, new):
        folder.mkdir()
    stored = Settings()
    stored.add_recent_folder(str(old))
    stored.add_recent_folder(str(deleted))
    deleted.rmdir()
    stored.add_recent_folder(str(new))
    assert stored.read("recent_folders", []) == [str(new), str(old)]


def test_recent_folders_round_trip_non_ascii_paths_with_commas(tmp_path, isolated_settings):
    folder = tmp_path / "árvíztűrő, tükörfúrógép"
    folder.mkdir()
    stored = Settings()
    stored.add_recent_folder(str(folder))
    stored.save()
    assert Settings().recent_folders() == [str(folder)]


def test_clear_recent_folders_forgets_all_of_them(tmp_path, isolated_settings):
    folder = tmp_path / "project"
    folder.mkdir()
    stored = Settings()
    stored.write("md_enabled", True)
    stored.add_recent_folder(str(folder))
    stored.clear_recent_folders()
    stored.save()
    assert stored.recent_folders() == []
    assert "recent_folders" not in isolated_settings.read_text(encoding="utf-8")


def test_choosing_a_recent_folder_that_no_longer_exists_drops_it_from_the_list(qtbot, tmp_path):
    kept, deleted = tmp_path / "kept", tmp_path / "deleted"
    kept.mkdir()
    deleted.mkdir()
    stored = Settings()
    stored.add_recent_folder(str(kept))
    stored.add_recent_folder(str(deleted))
    stored.save()
    window = MainWindow()
    qtbot.addWidget(window)
    combo = _recent_combo(window)
    assert _recent_items(combo) == [str(deleted), str(kept)]

    deleted.rmdir()
    combo.setCurrentIndex(1)  # the user picks the folder that is gone by now

    assert _recent_items(combo) == [str(kept)]
    assert combo.currentIndex() == 0

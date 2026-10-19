# -*- coding: utf-8 -*-
#
# this module saves and loads the settings
# they live in one INI file, %APPDATA%\CodePacker\settings.ini, and never in the registry:
# QSettings gets an explicit file path and the INI format

import os

from PySide6.QtCore import QSettings, QStandardPaths

from . import APP_NAME

SETTINGS_FILE_NAME = "settings.ini"

# tests point this at a temporary file; None means the real per-user location
settings_file_override = None


def default_settings_file():
    # %APPDATA% on windows; elsewhere the per-user config folder (e.g. ~/.config)
    base = os.environ.get("APPDATA") or QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericConfigLocation)
    return os.path.join(base, APP_NAME, SETTINGS_FILE_NAME)


def settings_file():
    if settings_file_override is not None:
        return settings_file_override
    return default_settings_file()


class Settings:

    def __init__(self):
        # nothing is created on disk here: QSettings makes the folder and the file
        # the first time it saves a change
        self.path = settings_file()
        self.store = QSettings(self.path, QSettings.Format.IniFormat)

    def read(self, key, default):
        # read a value; if it's missing, return the default
        value = self.store.value(key, default)

        # the INI file stores everything as text
        # so we convert it back based on the type of the default
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)

        if isinstance(default, int):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        if isinstance(default, list):
            if value is None:
                return default
            if isinstance(value, str):
                if value == "":
                    return []
                return [value]
            return list(value)

        return value

    def write(self, key, value):
        self.store.setValue(key, value)

    def save(self):
        # force it to actually flush to disk
        self.store.sync()

    # ------------------------------------------------------------
    # the recent-folders list, so it's quick to switch between them
    # ------------------------------------------------------------

    def recent_folders(self):
        # folders that were deleted or renamed since are left out; they also drop out of
        # the file the next time a folder is added
        folders = self.read("recent_folders", [])
        return [folder for folder in folders if os.path.isdir(folder)]

    def add_recent_folder(self, path):
        # put the newest folder at the front of the list, keep at most 8; returns the list
        folders = self.recent_folders()

        # if it's already in there, remove it first so it's not duplicated
        kept = []
        for folder in folders:
            if folder != path:
                kept.append(folder)

        kept.insert(0, path)

        if len(kept) > 8:
            kept = kept[:8]

        self.write("recent_folders", kept)
        return kept

    def clear_recent_folders(self):
        self.store.remove("recent_folders")

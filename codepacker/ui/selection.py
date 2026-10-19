# -*- coding: utf-8 -*-
#
# which scanned files go into the package: the one place the check marks live (plain Python,
# no Qt); the file tree only shows it, and the package is built from checked_entries()


class SelectionModel:

    def __init__(self, entries=()):
        # relative path -> core.FileEntry, in scan order; everything starts checked
        self.entries = {entry.relative_path: entry for entry in entries}
        self.checked = set(self.entries)

    def __len__(self):
        return len(self.entries)

    def is_checked(self, relative_path):
        return relative_path in self.checked

    def set_checked(self, relative_paths, checked):
        if checked:
            self.checked.update(path for path in relative_paths if path in self.entries)
        else:
            self.checked.difference_update(relative_paths)

    def visible(self, query):
        # the entries the filter text shows (a case-insensitive part of the relative path)
        query = query.strip().casefold()
        return [entry for path, entry in self.entries.items() if query in path.casefold()]

    def checked_entries(self):
        return [entry for path, entry in self.entries.items() if path in self.checked]

# -*- coding: utf-8 -*-
#
# this module walks a project folder and filters out the junk, there is no window/UI stuff
# here; it's kept separate on purpose so it can be tested on its own
#
# what gets skipped is listed in rules.py, building the output files is done in bundle.py
# links and junctions are never followed, every file it offers really lies inside the project
# folder (os.path.realpath), and paths beyond 260 characters are read with the \\?\ prefix

import os
import stat
from collections import Counter
from dataclasses import dataclass, field

from . import paths, rules, secret_scan

# a reparse point whose tag has this bit set stands for another place (symlink, junction, ...);
# a cloud placeholder (OneDrive) is a reparse point too, but it is the file itself
NAME_SURROGATE = 0x20000000


# ============================================================
# HELPER FUNCTIONS
# ============================================================


def format_size(num_bytes):
    # nice size formatting so the screen doesn't show 1234567 byte
    if num_bytes < 1024:
        return "{} B".format(num_bytes)
    if num_bytes < 1024 * 1024:
        return "{:.1f} kB".format(num_bytes / 1024.0)
    return "{:.2f} MB".format(num_bytes / (1024.0 * 1024.0))


def plural(count, noun):
    # "1 file", "3 files"
    return "{} {}{}".format(count, noun, "" if count == 1 else "s")


def read_bytes(path):
    # the whole file, or None if it can't be read
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


# ============================================================
# THE SCAN
# ============================================================


class FileEntry:
    # all the important data for one file, in one place
    # it's a class and not a dict because it reads better in the rest of the code

    def __init__(self, full_path, relative_path, size):
        self.full_path = full_path
        self.relative_path = relative_path
        self.size = size
        self.encoding = "utf-8"     # the codec the scan read it with (encoding.py)

    def extension(self):
        return os.path.splitext(self.relative_path)[1].lower()


@dataclass
class ScanResult:
    # what a scan found: the files that can go into the package, and everything left out
    # with its reason (a folder that was not even entered is one exclusion)
    included: list = field(default_factory=list)    # FileEntry, sorted by relative path
    excluded: list = field(default_factory=list)    # rules.Exclusion, sorted by relative path
    redactions: list = field(default_factory=list)  # secret_scan.Redaction, in scan order
    cancelled: bool = False                         # stopped early, the lists are partial
    root: str = ""                  # the folder every relative path starts from

    @property
    def secret_summary(self):
        files = 0
        for exclusion in self.excluded:
            if exclusion.kind == rules.SECRET:
                files = files + 1
        return secret_scan.SecretSummary(files, len(self.redactions))

    @property
    def stats(self):
        return {
            "included": len(self.included),
            "bytes": sum(entry.size for entry in self.included),
            "excluded": len(self.excluded),
            "excluded_by_kind": dict(Counter(e.kind for e in self.excluded)),
        }


def is_link(item):
    # a symlink, a junction or another reparse point that stands for a different place
    if item.is_symlink():
        return True
    try:
        info = item.stat(follow_symlinks=False)
    except OSError:
        return False
    if not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    return bool(getattr(info, "st_reparse_tag", NAME_SURROGATE) & NAME_SURROGATE)


def scan_project(root, max_size_kb, extra_excludes, log=None, progress=None, should_stop=None,
                 output_dir=None, only=None):
    # walk the project folder and sort every file into included or excluded
    #
    # root            - the project folder
    # max_size_kb     - files larger than this are skipped
    # extra_excludes  - the user-supplied glob list ("Also exclude")
    # log             - one line per exclusion (names and rule ids only), can be None
    # progress        - called every so often so progress is visible
    # should_stop     - if this returns True we stop (the result is marked cancelled)
    # output_dir      - where the package goes; inside the project it is left out
    # only            - only(relative path, is a folder) says what an ad-hoc package wants;
    #                   the rest is not looked at (scan_selection)

    result = ScanResult()
    max_size = max_size_kb * 1024
    extra_rules = rules.user_rules(extra_excludes)
    root = paths.clean_path(root)
    result.root = root
    real_root = paths.real_path(root)
    output_real = None
    if output_dir and paths.relative_inside(output_dir, root) is not None:
        output_real = paths.real_path(output_dir)
    secret_folders = Counter()  # the files of a secret folder get one log line together

    def skip(rule, relative_path):
        result.excluded.append(rule.exclusion(relative_path))
        folder = None
        if rule.id == rules.SECRET_FOLDER_ID:
            folder = rules.secret_folder_of(relative_path)
        if folder is not None:
            secret_folders[(folder, rule.reason)] += 1
        elif log is not None:
            log("skipped {} \u2014 {} [{}]".format(relative_path, rule.reason, rule.id))

    checked = 0
    pending = [("", paths.long_path(root))]
    while pending:
        if should_stop is not None and should_stop():
            result.cancelled = True
            break
        prefix, folder = pending.pop()
        try:
            with os.scandir(folder) as found:
                items = sorted(found, key=lambda item: item.name)
        except OSError:
            skip(rules.UNREADABLE, prefix.rstrip("/") or ".")
            continue

        subfolders = []
        for item in items:
            if should_stop is not None and should_stop():
                result.cancelled = True
                pending = []
                break
            relative_path = prefix + item.name
            if only is not None and not only(relative_path, item.is_dir()):
                continue

            # links and junctions are never followed, whatever they point to
            if is_link(item):
                skip(rules.LINK_RULE, relative_path)
                continue

            if item.is_dir(follow_symlinks=False):
                # we don't even enter the excluded folders
                rule = rules.match_dir(relative_path, extra_rules)
                if (rule is None and output_real is not None
                        and paths.real_path(item.path) == output_real):
                    rule = rules.SELF_OUTPUT_RULE
                if rule is not None:
                    skip(rule, relative_path)
                else:
                    subfolders.append((relative_path + "/", item.path))
                continue

            checked = checked + 1
            if progress is not None and checked % 200 == 0:
                progress(checked, len(result.included))
            entry, rule = check_file(item, relative_path, root, real_root, max_size,
                                     extra_rules, result, log)
            if rule is not None:
                skip(rule, relative_path)
            else:
                result.included.append(entry)

        # depth first, in name order
        if not result.cancelled:
            pending.extend(reversed(subfolders))

    result.included.sort(key=lambda entry: entry.relative_path)
    result.excluded.sort(key=lambda exclusion: exclusion.rel_path)

    if log is not None:
        for (folder, reason), count in sorted(secret_folders.items()):
            log("skipped {} ({}) \u2014 {} [{}]".format(
                folder, plural(count, "file"), reason, rules.SECRET_FOLDER_ID))
        summary = result.secret_summary
        log("secrets: {} file(s) excluded, {} token(s) redacted".format(
            summary.files_excluded, summary.tokens_redacted))
    return result


def scan_selection(selected_paths, max_size_kb, extra_excludes, log=None, progress=None,
                   should_stop=None, output_dir=None):
    # an ad-hoc package: the chosen files and folders, with paths relative to their common
    # parent folder (result.root) and every rule of a project scan; files that sit in a
    # folder holding secrets stay out even when that folder is the common parent itself
    items = [paths.clean_path(path) for path in selected_paths]
    root = os.path.commonpath([os.path.dirname(item) for item in items])
    relative = [os.path.relpath(item, root).replace(os.sep, "/") for item in items]

    if rules.secret_folder_of(root.replace(os.sep, "/") + "/") is not None:
        result = ScanResult(root=root)
        for relative_path in sorted(relative):
            result.excluded.append(rules.SECRET_FOLDER.exclusion(relative_path))
            if log is not None:
                log("skipped {} \u2014 {} [{}]".format(
                    relative_path, rules.SECRET_FOLDER.reason, rules.SECRET_FOLDER.id))
        return result

    folders = [path.casefold() for path, item in zip(relative, items) if os.path.isdir(item)]
    files = {path.casefold() for path, item in zip(relative, items) if not os.path.isdir(item)}

    def only(relative_path, is_folder):
        path = relative_path.casefold()
        if any(path == folder or path.startswith(folder + "/") for folder in folders):
            return True
        if is_folder:
            return any(chosen.startswith(path + "/") for chosen in [*files, *folders])
        return path in files

    return scan_project(root, max_size_kb, extra_excludes, log, progress, should_stop,
                        output_dir, only)


def check_file(item, relative_path, root, real_root, max_size, extra_rules, result, log):
    # (the FileEntry, None) for a file that can go in, (None, the rule) for one that stays out

    # the name rules come first, the secret ones before all others: a secret file can never go in
    rule = rules.match_file(relative_path, extra_rules)

    # if there's no extension we only include it if we recognize the name
    if (rule is None and os.path.splitext(item.name)[1] == ""
            and not rules.is_known_extensionless(item.name)):
        rule = rules.NO_EXTENSION
    if rule is not None:
        return None, rule

    if not item.is_file(follow_symlinks=False) or not paths.is_inside(item.path, real_root):
        return None, rules.OUTSIDE_PROJECT

    try:
        size = item.stat(follow_symlinks=False).st_size
    except OSError:
        return None, rules.UNREADABLE
    if size == 0:
        # an empty file isn't worth including, it just takes up space
        return None, rules.EMPTY_FILE
    if size > max_size:
        return None, rules.TOO_LARGE

    content = read_bytes(item.path)
    if content is None:
        return None, rules.UNREADABLE

    # the content check: binary content or a private key keeps the file out; tokens are only
    # noted here, the package gets them replaced when it's built (bundle.py runs the very same
    # check, so what is noted here is exactly what gets replaced)
    inspection = secret_scan.inspect(content)
    if inspection.rule is not None:
        return None, inspection.rule
    for token_type, line in inspection.findings:
        result.redactions.append(secret_scan.Redaction(relative_path, token_type, line))
        if log is not None:
            log("token redacted in the package: {}, line {} [{}]".format(
                relative_path, line, token_type))

    if inspection.codec != "utf-8" and log is not None:
        log("read {} as {}".format(relative_path, inspection.codec))
    full_path = os.path.join(root, *relative_path.split("/"))
    entry = FileEntry(full_path, relative_path, size)
    entry.encoding = inspection.codec
    return entry, None

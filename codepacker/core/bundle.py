# -*- coding: utf-8 -*-
#
# this module builds the output files from the scanned file list: one or more MD files,
# or a zip encoded as base64 text; there is no window/UI stuff here either
#
# the MD is split by size: every part stays under the limit unless a single file is larger
# on its own (it then gets a part of its own and a warning), and a file is never cut in two

import base64
import datetime
import io
import math
import os
import re
import zipfile
from dataclasses import dataclass, field

from . import paths, rules, secret_scan
from .scanner import format_size, plural

# which extension maps to which code block language in the md
LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".pyw": "python", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".jsx": "jsx", ".ts": "typescript", ".tsx": "tsx",
    ".json": "json", ".jsonc": "json", ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".md": "markdown", ".markdown": "markdown", ".yml": "yaml", ".yaml": "yaml",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".bat": "batch",
    ".cmd": "batch", ".ps1": "powershell", ".sql": "sql", ".xml": "xml",
    ".java": "java", ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp",
    ".cxx": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp", ".go": "go",
    ".rs": "rust", ".php": "php", ".rb": "ruby", ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin", ".dart": "dart", ".lua": "lua",
    ".r": "r", ".jl": "julia", ".pl": "perl", ".toml": "toml",
    ".ini": "ini", ".cfg": "ini", ".conf": "ini", ".txt": "text",
    ".csv": "csv", ".vue": "vue", ".svelte": "svelte", ".graphql": "graphql",
    ".proto": "protobuf", ".dockerfile": "dockerfile", ".tf": "hcl",
}

# "## FILE: " + "\n\n" + "```" + "\n" (after the language) + "\n" + "```" + "\n\n"
BLOCK_OVERHEAD = 21
# a zip entry: local header (30) + central directory record (46), each followed by the name
ZIP_ENTRY_OVERHEAD = 76
ZIP_END_RECORD = 22
BASE64_LINE_LENGTH = 200


class Cancelled(Exception):
    # the user stopped the build; whatever it had written is deleted again
    pass


@dataclass
class BundleResult:
    # what one output format produced
    paths: list = field(default_factory=list)       # the files written, in order
    packed: int = 0                                 # how many files went in
    errors: list = field(default_factory=list)      # relative paths that could not be read
    oversized: list = field(default_factory=list)   # parts over the size limit
    name: str = ""                                  # "md" or "b64"
    failure: str = ""                               # why the format failed, "" if it didn't

    @property
    def ok(self):
        return self.failure == "" and not self.errors

    @property
    def line(self):
        # the one-line result the window and the command line print: "md: ok, 3 parts"
        if self.failure:
            return "{}: FAILED {}".format(self.name, self.failure)
        text = self.name + ": ok"
        if len(self.paths) > 1:
            text = text + ", {} parts".format(len(self.paths))
        if self.errors:
            text = text + ", {} could not be read".format(plural(len(self.errors), "file"))
        return text


# ============================================================
# HELPER FUNCTIONS
# ============================================================


def guess_language(relative_path):
    # figure out which language tag the code block should get
    name = os.path.basename(relative_path).lower()
    extension = os.path.splitext(name)[1].lower()

    if extension in LANGUAGE_BY_EXTENSION:
        return LANGUAGE_BY_EXTENSION[extension]

    # dockerfile and makefile aren't matched by extension
    if name.startswith("dockerfile"):
        return "dockerfile"
    if name.startswith("makefile"):
        return "makefile"

    return ""


def utf8_length(text):
    return len(text.encode("utf-8"))


def inspect_for_bundle(entry, log=None, root=None):
    # the content check of one file for a package (secret_scan.Inspection), OSError if it
    # can't be read
    #
    # None if the file must stay out: the scan never offers such a file, but whoever passes one
    # in anyway gets it refused here, by its name (as given, on disk, and where it really lies
    # in the project root, so a secret folder counts whatever relative path is passed), by
    # lying outside the root, by binary content that can't be checked, or by a private key
    names = [entry.relative_path, os.path.basename(entry.full_path)]
    if root is not None:
        real_relative_path = paths.relative_inside(entry.full_path, root)
        if real_relative_path is None:
            return refuse(entry, rules.OUTSIDE_PROJECT, log)
        names.append(real_relative_path)
    for name in names:
        rule = rules.secret_rule_for(name)
        if rule is not None:
            return refuse(entry, rule, log)

    with open(paths.long_path(entry.full_path), "rb") as handle:
        raw = handle.read()
    inspection = secret_scan.inspect(raw)
    if inspection.rule is not None:
        return refuse(entry, inspection.rule, log)
    return inspection


def bundle_bytes(entry, log=None, root=None):
    # the bytes this file puts into the zip: the file itself with every token replaced by
    # "[REDACTED:<type>]" (the user's own file is never touched); None if refused
    inspection = inspect_for_bundle(entry, log, root)
    return None if inspection is None else inspection.data


def bundle_text(entry, log=None, root=None):
    # the file as text for the MD, decoded in its own codec, with its tokens replaced, without
    # a byte-order mark and with "\n" line endings; None if refused
    inspection = inspect_for_bundle(entry, log, root)
    if inspection is None:
        return None
    return inspection.text.replace("\r\n", "\n").replace("\r", "\n")


def refuse(entry, rule, log):
    # a file stays out of the package; the log gets its name and the rule, nothing else
    if log is not None:
        what = "secret file" if rule.kind == rules.SECRET else "file"
        log("{} refused: {} ({}) [{}]".format(what, entry.relative_path, rule.reason, rule.id))
    return None


def unreadable(entry, log, result):
    # a file that disappeared or got locked since the scan: skipped, the rest goes on
    result.errors.append(entry.relative_path)
    if log is not None:
        log("skipped {} — {} [{}]".format(
            entry.relative_path, rules.UNREADABLE.reason, rules.UNREADABLE.id))


# ============================================================
# BUILDING THE MD
# ============================================================


def build_header(project_name, entries, part_number=0, part_count=0):
    # the header contains the project name and the full file structure
    # this matters so the model immediately sees the project's shape
    text = ""

    if part_count > 1:
        text = text + "# PROJECT: {} ({}/{} part)\n\n".format(
            project_name, part_number, part_count)
    else:
        text = text + "# PROJECT: {}\n\n".format(project_name)

    text = text + "Generated: {}\n".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    text = text + "File count: {}\n".format(len(entries))

    total_size = 0
    for entry in entries:
        total_size = total_size + entry.size
    text = text + "Total size: {}\n\n".format(format_size(total_size))

    if part_count > 1:
        text = text + ("This project was uploaded in {} parts. "
                       "The full file list is in the first part.\n\n").format(part_count)

    text = text + "## File structure\n\n```\n"
    for entry in entries:
        text = text + entry.relative_path + "\n"
    text = text + "```\n\n---\n\n"

    return text


def continuation_header(project_name, part_number, part_count):
    # later parts don't repeat the full file list again
    return ("# PROJECT: {} ({}/{} part)\n\n"
            "This is a continuation of the previous part.\n\n---\n\n").format(
                project_name, part_number, part_count)


def build_code_block(entry, content):
    # turn one file into an md code block
    language = guess_language(entry.relative_path)

    # if the file itself contains a backtick, fence the block with more backticks
    # otherwise it would break the whole md structure
    fence = "```"
    while fence in content:
        fence = fence + "`"

    block = "## FILE: {}\n\n{}{}\n{}\n{}\n\n".format(
        entry.relative_path, fence, language, content, fence)

    return block


def stop_if_asked(should_stop):
    if should_stop is not None and should_stop():
        raise Cancelled()


def collect_blocks(entries, result, progress=None, log=None, root=None, should_stop=None):
    # [(entry, its code block)] of the files that go in, in order
    blocks = []
    for done, entry in enumerate(entries, 1):
        stop_if_asked(should_stop)
        try:
            content = bundle_text(entry, log, root)
        except OSError:
            unreadable(entry, log, result)
            content = None
        if content is not None:
            blocks.append((entry, build_code_block(entry, content)))
        if progress is not None:
            progress(done, len(entries))
    result.packed = len(blocks)
    return blocks


def plan_parts(project_name, blocks, max_part_bytes):
    # [(header, [block, ...], the entries)] in order; one part when there is no limit or all fits
    packed = [entry for entry, _ in blocks]
    single = build_header(project_name, packed)
    total = utf8_length(single) + sum(utf8_length(block) for _, block in blocks)
    if not max_part_bytes or total <= max_part_bytes:
        return [(single, [block for _, block in blocks], packed)]

    # plan with the longest part numbers there could be: the real headers are never longer
    most = len(blocks) + 1
    size = utf8_length(build_header(project_name, packed, most, most))
    later = utf8_length(continuation_header(project_name, most, most))
    groups = [[]]
    for entry, block in blocks:
        length = utf8_length(block)
        if groups[-1] and size + length > max_part_bytes:
            groups.append([])
            size = later
        groups[-1].append((entry, block))
        size = size + length

    count = len(groups)
    parts = []
    for number, group in enumerate(groups, 1):
        if number == 1:
            header = build_header(project_name, packed, 1, count)
        else:
            header = continuation_header(project_name, number, count)
        parts.append((header, [block for _, block in group], [entry for entry, _ in group]))
    return parts


def part_file_name(project_name, number, count):
    if count == 1:
        return "{}_combined.md".format(project_name)
    return "{}_combined_part{}.md".format(project_name, number)


def markdown_text(project_name, entries, log=None, root=None):
    # the whole MD as one string, for the clipboard (nothing is written); (text, BundleResult)
    result = BundleResult(name="md")
    blocks = collect_blocks(entries, result, None, log, root)
    [(header, part_blocks, _)] = plan_parts(project_name, blocks, 0)
    return header + "".join(part_blocks), result


def estimate_tokens(characters):
    # a rough token count of a text for an AI chat: about four characters per token
    return characters // 4


def remove_stale_parts(project_name, output_dir, count):
    # a previous run may have written more parts (or one file instead of parts): those files
    # would be uploaded with the new ones by mistake; only this project's own names go
    pattern = re.compile(re.escape(project_name) + r"_combined(?:_part(\d+))?\.md",
                         re.IGNORECASE)
    for name in os.listdir(output_dir):
        match = pattern.fullmatch(name)
        if match is None:
            continue
        number = match.group(1)
        stale = (count > 1 and number is None) or (
            number is not None and (count == 1 or int(number) > count))
        if stale:
            os.remove(os.path.join(output_dir, name))


def write_markdown(project_name, entries, output_dir, max_part_bytes=0, progress=None,
                   log=None, root=None, should_stop=None):
    # generate the md file(s), parts of at most max_part_bytes (0: one file); returns a
    # BundleResult; log gets a line for every file that is refused (a secret name, binary
    # content that can't be checked, a private key inside) or unreadable, names and rule ids only
    # a run that fails or is cancelled (Cancelled) deletes the parts it has written
    result = BundleResult(name="md")
    blocks = collect_blocks(entries, result, progress, log, root, should_stop)
    parts = plan_parts(project_name, blocks, max_part_bytes)
    remove_stale_parts(project_name, output_dir, len(parts))

    try:
        for number, (header, part_blocks, part_entries) in enumerate(parts, 1):
            stop_if_asked(should_stop)
            file_name = part_file_name(project_name, number, len(parts))
            path = os.path.join(output_dir, file_name)
            text = header + "".join(part_blocks)
            result.paths.append(path)
            with open(path, "w", encoding="utf-8", newline="\n") as out:
                out.write(text)
            warn_if_oversized(result, path, text, max_part_bytes, part_entries, log)
    except BaseException:
        remove_files(result.paths)
        raise
    return result


def warn_if_oversized(result, path, text, max_part_bytes, part_entries, log):
    size = utf8_length(text)
    if max_part_bytes and size > max_part_bytes:
        result.oversized.append(path)
        if log is not None:
            log("warning: {} is {}, over the part size limit ({}): {} does not fit in "
                "a smaller part".format(os.path.basename(path), format_size(size),
                                        format_size(max_part_bytes),
                                        part_entries[0].relative_path))


def remove_files(file_paths):
    for path in file_paths:
        try:
            os.remove(path)
        except OSError:
            pass



# ============================================================
# BUILDING THE BASE64 ZIP
# ============================================================


def base64_header(project_name, file_count):
    return ("# THIS IS A BASE64-ENCODED ZIP FILE\n"
            "# project name: {}\n"
            "# file count: {}\n"
            "# generated: {}\n"
            "#\n"
            "# decode and unzip in your sandbox:\n"
            "#   grep -v '^#' thisfile.txt | tr -d '\\n' | base64 -d > p.zip\n"
            "#   unzip p.zip\n"
            "#\n").format(project_name, file_count,
                          datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))


def write_base64_zip(project_name, entries, output_dir, progress=None, log=None, root=None,
                     should_stop=None):
    # build a zip in memory, then write it base64-encoded into a txt file (UTF-8, written to a
    # temporary name first, so a failed run never leaves half a file behind); returns a
    # BundleResult
    # an AI chat with a code sandbox can turn it back into the zip with a base64 -d command
    result = BundleResult(name="b64")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for done, entry in enumerate(entries, 1):
            stop_if_asked(should_stop)
            try:
                data = bundle_bytes(entry, log, root)
                if data is not None:
                    # the file's name, date and attributes, but the content with its tokens
                    # replaced; a date before 1980 (which zip can't store) becomes 1980
                    info = zipfile.ZipInfo.from_file(
                        paths.long_path(entry.full_path), project_name + "/" + entry.relative_path,
                        strict_timestamps=False)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data)
                    result.packed = result.packed + 1
            except OSError:
                unreadable(entry, log, result)
            if progress is not None:
                progress(done, len(entries))

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    txt_path = os.path.join(output_dir, "{}_zip.b64.txt".format(project_name))
    temporary = txt_path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as out:
            out.write(base64_header(project_name, result.packed))
            # wrap into 200-character lines so there's no single endless line
            for start in range(0, len(encoded), BASE64_LINE_LENGTH):
                out.write(encoded[start:start + BASE64_LINE_LENGTH] + "\n")
        os.replace(temporary, txt_path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

    result.paths.append(txt_path)
    return result


# ============================================================
# BOTH FORMATS, AS THE WINDOW AND THE COMMAND LINE BUILD THEM
# ============================================================


def build_package(project_name, entries, output_dir, md=True, b64=False, max_part_bytes=0,
                  root=None, progress=None, log=None, should_stop=None):
    # every chosen format, one BundleResult each (a format that fails is reported in its
    # result, the others still run); Cancelled when should_stop() turns true, after deleting
    # everything this run has written
    writers = []
    if md:
        writers.append(("md", lambda step: write_markdown(
            project_name, entries, output_dir, max_part_bytes, step, log, root, should_stop)))
    if b64:
        writers.append(("b64", lambda step: write_base64_zip(
            project_name, entries, output_dir, step, log, root, should_stop)))

    results = []
    try:
        for offset, (name, write) in enumerate(writers):
            step = None
            if progress is not None:
                # one bar for all formats
                step = (lambda done, total, offset=offset:
                        progress(offset * total + done, len(writers) * total))
            try:
                result = write(step)
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                result = BundleResult(name=name, failure=str(error) or type(error).__name__)
            results.append(result)
    except Cancelled:
        for result in results:
            remove_files(result.paths)
        raise
    return results


# ============================================================
# ESTIMATES, SO THE USER CAN SEE WHAT'S COMING
# ============================================================


def compressed_estimate(size):
    # deflate barely shrinks a few dozen bytes; longer source text shrinks to about a third
    if size <= 100:
        return min(size + 3, int(6 + size * 0.85))
    return int(91 + (size - 100) * 0.32)


def estimate_sizes(entries, project_name="project"):
    # (md bytes, base64 txt bytes), from the file sizes alone (nothing is read): the headers
    # and the file list are built exactly, the contents are taken as they are on disk
    md_estimate = utf8_length(build_header(project_name, entries))
    zip_estimate = ZIP_END_RECORD
    prefix = utf8_length(project_name) + 1
    for entry in entries:
        name = utf8_length(entry.relative_path)
        md_estimate = (md_estimate + BLOCK_OVERHEAD + name
                       + len(guess_language(entry.relative_path)) + entry.size)
        zip_estimate = (zip_estimate + ZIP_ENTRY_OVERHEAD + 2 * (prefix + name)
                        + compressed_estimate(entry.size))

    # base64 turns every 3 bytes into 4, plus the line breaks and the header
    encoded = 4 * math.ceil(zip_estimate / 3)
    b64_estimate = (utf8_length(base64_header(project_name, len(entries))) + encoded
                    + math.ceil(encoded / BASE64_LINE_LENGTH))
    return md_estimate, b64_estimate


def extension_stats(entries):
    # breakdown by extension, so it's visible what's in there and how much
    by_extension = {}
    for entry in entries:
        extension = entry.extension()
        if extension == "":
            extension = "(none)"
        if extension not in by_extension:
            by_extension[extension] = {"count": 0, "size": 0}
        by_extension[extension]["count"] = by_extension[extension]["count"] + 1
        by_extension[extension]["size"] = by_extension[extension]["size"] + entry.size

    # sort by size, descending
    rows = []
    for extension in by_extension:
        rows.append((extension, by_extension[extension]["count"], by_extension[extension]["size"]))
    rows.sort(key=lambda x: x[2], reverse=True)

    return rows

# -*- coding: utf-8 -*-
#
# the command line: python -m codepacker <path...> [--md] [--b64] [--max-part SIZE] [--out DIR]
#                                         [--exclude GLOB...] [--quiet]
# one folder is a project; files (or several paths) make an ad-hoc package of just those
# it uses the core alone and never imports Qt, so it runs without PySide6 installed
# exit code: 0 when every format is written and no file was left out by an error, 1 otherwise

import argparse
import os
import sys

from . import APP_NAME, __version__, core

DEFAULT_MAX_FILE_KB = 300
SIZE_UNITS = {"": 1, "b": 1, "k": 1024, "kb": 1024, "m": 1024 * 1024, "mb": 1024 * 1024}


def parse_size(text):
    # "500k", "2M", "750kb" or plain bytes -> bytes
    cleaned = text.strip().lower()
    number = cleaned.rstrip("kmb")
    unit = cleaned[len(number):]
    if not number.isdigit() or unit not in SIZE_UNITS:
        raise argparse.ArgumentTypeError("not a size: {!r} (try 500k or 2M)".format(text))
    return int(number) * SIZE_UNITS[unit]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m codepacker",
        description="Bundle a source folder (or some files) into an upload-ready Markdown "
                    "file for AI chats, without secrets.")
    parser.add_argument("paths", nargs="+", metavar="path",
                        help="a project folder, or the files and folders of an ad-hoc package")
    parser.add_argument("--md", action="store_true", help="write the Markdown file (default)")
    parser.add_argument("--b64", action="store_true", help="write the base64 zip TXT")
    parser.add_argument("--max-part", type=parse_size, default=0, metavar="SIZE",
                        help="split the Markdown into parts of at most SIZE (e.g. 500k, 2M)")
    parser.add_argument("--out", metavar="DIR",
                        help="output folder (default: <project>_codepacker next to it)")
    parser.add_argument("--exclude", nargs="+", action="extend", default=[], metavar="GLOB",
                        help="also exclude these globs (e.g. *.bak docs/** tests/)")
    parser.add_argument("--quiet", action="store_true",
                        help="print only the result lines, not every skipped file")
    parser.add_argument("--version", action="version",
                        version="{} {}".format(APP_NAME, __version__))
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    say = print
    log = None if arguments.quiet else print

    missing = [path for path in arguments.paths if not os.path.exists(path)]
    if missing:
        say("error: not found: " + ", ".join(missing), file=sys.stderr)
        return 1

    excludes = ",".join(arguments.exclude)
    single_folder = len(arguments.paths) == 1 and os.path.isdir(arguments.paths[0])
    if single_folder:
        root = core.clean_path(arguments.paths[0])
    else:
        root = os.path.commonpath([os.path.dirname(core.clean_path(path))
                                   for path in arguments.paths])
    output_dir = core.clean_path(arguments.out) if arguments.out else core.default_output_dir(root)
    if core.real_path(output_dir) == core.real_path(root):
        say("error: the output folder can't be the project folder itself", file=sys.stderr)
        return 1
    if core.relative_inside(output_dir, root) is not None:
        say("warning: the output folder is inside the project, the scan leaves it out")

    if single_folder:
        result = core.scan_project(root, DEFAULT_MAX_FILE_KB, excludes, log=log,
                                   output_dir=output_dir)
    else:
        result = core.scan_selection(arguments.paths, DEFAULT_MAX_FILE_KB, excludes, log=log,
                                     output_dir=output_dir)
    errors = [exclusion for exclusion in result.excluded if exclusion.kind == "error"]
    if not result.included:
        say("error: no file to pack, every file was excluded", file=sys.stderr)
        return 1

    os.makedirs(output_dir, exist_ok=True)
    results = core.build_package(
        core.project_name(result.root), result.included, output_dir,
        md=arguments.md or not arguments.b64, b64=arguments.b64,
        max_part_bytes=arguments.max_part, root=result.root, log=log)
    for written in results:
        for path in written.paths:
            say("written: " + path)
        say(written.line)
    if errors:
        say("{} left out by a read error".format(core.plural(len(errors), "file")))
    return 0 if not errors and all(written.ok for written in results) else 1


if __name__ == "__main__":
    sys.exit(main())

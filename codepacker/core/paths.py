# -*- coding: utf-8 -*-
#
# path helpers for the scanner and the bundle builder: the project folder as typed or dropped,
# long paths on Windows, where a file really is (links resolved) and the default output folder

import os
import sys

OUTPUT_SUFFIX = "_codepacker"
LONG_PREFIX = "\\\\?\\"


def clean_path(path):
    # absolute, "/" and "\" both accepted, no trailing separator (a drive root keeps its own)
    return os.path.abspath(os.path.normpath(path))


def project_name(root):
    return os.path.basename(clean_path(root)) or "project"


def default_output_dir(root):
    # <parent>/<project name>_codepacker, next to the project, whatever separator it ends in
    clean = clean_path(root)
    return os.path.join(os.path.dirname(clean), project_name(clean) + OUTPUT_SUFFIX)


def long_path(path):
    # the form Windows opens beyond 260 characters, even with long paths disabled
    text = clean_path(path)
    if sys.platform != "win32" or text.startswith(LONG_PREFIX):
        return text
    if text.startswith("\\\\"):
        return LONG_PREFIX + "UNC\\" + text[2:]
    return LONG_PREFIX + text


def real_path(path):
    # where the path really leads (links resolved), comparable with another real_path()
    real = os.path.realpath(long_path(path))
    if real.startswith(LONG_PREFIX + "UNC\\"):
        real = "\\\\" + real[len(LONG_PREFIX) + 4:]
    elif real.startswith(LONG_PREFIX):
        real = real[len(LONG_PREFIX):]
    return os.path.normcase(real)


def is_inside(path, real_root):
    # whether the path really lies below the folder whose real_path() is real_root
    return real_path(path).startswith(real_root.rstrip(os.sep) + os.sep)


def relative_inside(path, root):
    # the path's real location relative to the root's ("a/b.txt"), or None when it is outside
    real, real_root = real_path(path), real_path(root).rstrip(os.sep)
    if not real.startswith(real_root + os.sep):
        return None
    return real[len(real_root) + 1:].replace(os.sep, "/")

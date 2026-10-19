# -*- coding: utf-8 -*-
#
# the core: scanning a project folder and bundling the chosen files
# pure Python on purpose, it must never import Qt (tests/test_architecture.py checks this)
#
#   rules.py        what is never included, and why
#   paths.py        long paths, real locations, the default output folder
#   secret_scan.py  private keys and tokens found inside the files
#   scanner.py      walking the folder and filtering
#   bundle.py       building the MD and base64 outputs, size estimates and statistics

from .bundle import (
    BundleResult,
    Cancelled,
    build_package,
    estimate_sizes,
    estimate_tokens,
    extension_stats,
    markdown_text,
    write_base64_zip,
    write_markdown,
)
from .paths import clean_path, default_output_dir, project_name, real_path, relative_inside
from .rules import Exclusion
from .scanner import FileEntry, ScanResult, format_size, plural, scan_project, scan_selection

__all__ = [
    "BundleResult",
    "Cancelled",
    "build_package",
    "Exclusion",
    "FileEntry",
    "ScanResult",
    "clean_path",
    "default_output_dir",
    "estimate_sizes",
    "estimate_tokens",
    "extension_stats",
    "format_size",
    "markdown_text",
    "plural",
    "project_name",
    "real_path",
    "relative_inside",
    "scan_project",
    "scan_selection",
    "write_base64_zip",
    "write_markdown",
]

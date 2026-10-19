"""Encoding detection (spec C-5): byte-order marks, UTF-16 without a mark, legacy code pages."""

import codecs
from pathlib import Path

import pytest

from codepacker import core
from codepacker.core import encoding
from fixtures import CP1250_FILE, LATIN1_FILE, UTF8_BOM_FILE, UTF16_FILE, hostile_tree

TEXT = "Write-Host 'árvíztűrő'\r\n"


def test_a_byte_order_mark_picks_the_codec_and_is_not_part_of_the_text():
    for mark, codec in [(codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
                        (codecs.BOM_UTF16_BE, "utf-16-be"), (codecs.BOM_UTF32_LE, "utf-32-le"),
                        (codecs.BOM_UTF32_BE, "utf-32-be")]:
        assert encoding.decode(mark + TEXT.encode(codec)) == (codec, TEXT, mark)


def test_utf16_without_a_mark_text_in_legacy_code_pages_and_binary_content():
    assert encoding.decode(TEXT.encode("utf-16-le"))[:2] == ("utf-16-le", TEXT)
    assert encoding.decode(TEXT.encode("utf-16-be"))[:2] == ("utf-16-be", TEXT)
    assert encoding.decode("őrült ŐŰ".encode("cp1250"))[:2] == ("cp1250", "őrült ŐŰ")
    assert encoding.decode(b"\x81\xe9")[0] == "latin-1"  # 0x81 is undefined in cp1250
    assert encoding.decode(b"\x00\x01\x02\x03 binary\xff") is None
    assert encoding.decode(bytes(range(1, 9)) * 20) is None  # control characters only


@pytest.fixture(scope="module")
def hostile_bundle(tmp_path_factory):
    root = hostile_tree(tmp_path_factory.mktemp("encoding") / "project", junctions=False)
    log = []
    result = core.scan_project(str(root), 300, "", log=log.append)
    output = tmp_path_factory.mktemp("encoding_output")
    [md] = core.write_markdown("project", result.included, str(output), root=str(root)).paths
    return result, log, Path(md).read_text(encoding="utf-8")


def test_legacy_and_utf16_files_reach_the_md_as_clean_text(hostile_bundle):
    result, log, md = hostile_bundle
    codecs_by_path = {entry.relative_path: entry.encoding for entry in result.included}
    assert codecs_by_path[CP1250_FILE] == "cp1250"
    assert codecs_by_path[UTF16_FILE] == "utf-16-le"
    assert codecs_by_path[UTF8_BOM_FILE] == "utf-8"
    assert f"read {CP1250_FILE} as cp1250" in log
    assert not [line for line in log if line.startswith(f"read {UTF8_BOM_FILE} ")]
    assert "árvíztűrő tükörfúrógép ŐŰ" in md
    assert "Write-Host 'UTF-16 PowerShell'" in md
    assert LATIN1_FILE in codecs_by_path
    assert "�" not in md and "﻿" not in md

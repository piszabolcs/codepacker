"""Output correctness (spec C-1, C-2, C-6, C-7, C-14, C-16): size-based parts, base64, estimates."""

import base64
import io
import os
import re
import time
import zipfile
from pathlib import Path

import pytest

from codepacker import core
from fixtures import hostile_tree, long_path_safe

FENCE = re.compile(r"^(`{3,})", re.MULTILINE)


def _project(make_project, root):
    files = {f"src/module_{index:02d}.py": f"value = {index}\n" + "# padding\n" * (index * 4)
             for index in range(30)}
    files["docs/fenced.md"] = "Example:\n\n```python\nprint('inner fence')\n```\n"
    return make_project(root, files)


def _scan(root):
    return core.scan_project(str(root), 300, "").included


def _parts(paths):
    return [Path(path).read_text(encoding="utf-8") for path in paths]


def _unzip(b64_path):
    lines = Path(b64_path).read_text(encoding="utf-8").splitlines()
    payload = "".join(line for line in lines if not line.startswith("#"))
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(payload, validate=True)))


def test_parts_respect_the_size_limit_and_keep_every_file_once_in_order(make_project, tmp_path):
    root = _project(make_project, tmp_path / "proj")
    entries = _scan(root)
    output = tmp_path / "out"
    output.mkdir()
    result = core.write_markdown("proj", entries, str(output), 2000, root=str(root))

    texts = _parts(result.paths)
    assert len(texts) > 3
    assert [Path(path).name for path in result.paths] == [
        f"proj_combined_part{number}.md" for number in range(1, len(texts) + 1)]
    assert result.oversized == []
    assert all(len(text.encode("utf-8")) <= 2000 for text in texts)
    assert "## File structure" in texts[0]
    assert not [text for text in texts[1:] if "## File structure" in text]
    files = [name for text in texts for name in re.findall(r"^## FILE: (.*)$", text, re.MULTILINE)]
    assert files == [entry.relative_path for entry in entries]
    for text in texts:  # every fence that opens a block closes it again
        blocks = text.split("\n## FILE: ")[1:]
        for block in blocks:
            opening = FENCE.search(block).group(1)
            assert block.rstrip().endswith("\n" + opening)


def test_a_file_larger_than_the_limit_gets_a_part_of_its_own_and_a_warning(
    make_project, tmp_path
):
    root = make_project(tmp_path / "proj", {"a.py": "a = 1\n", "big.py": "# x\n" * 2000,
                                            "c.py": "c = 3\n"})
    log = []
    result = core.write_markdown("proj", _scan(root), str(tmp_path), 3000, log=log.append,
                                 root=str(root))
    texts = _parts(result.paths)
    assert [re.findall(r"^## FILE: (.*)$", text, re.MULTILINE) for text in texts] == [
        ["a.py"], ["big.py"], ["c.py"]]
    assert result.oversized == [result.paths[1]]
    assert [line for line in log if line.startswith("warning: proj_combined_part2.md is")
            and "big.py" in line]


def test_stale_parts_of_an_earlier_run_are_removed_and_nothing_else(make_project, tmp_path):
    root = _project(make_project, tmp_path / "proj")
    entries = _scan(root)
    output = tmp_path / "out"
    output.mkdir()
    (output / "other_combined_part9.md").write_text("another project\n", encoding="utf-8")
    (output / "proj_combined_part1.md.bak").write_text("a backup\n", encoding="utf-8")

    many = core.write_markdown("proj", entries, str(output), 2000, root=str(root)).paths
    fewer = core.write_markdown("proj", entries, str(output), 6000, root=str(root)).paths
    assert len(fewer) < len(many)
    names = sorted(path.name for path in output.iterdir())
    assert names == sorted([Path(path).name for path in fewer]
                           + ["other_combined_part9.md", "proj_combined_part1.md.bak"])

    single = core.write_markdown("proj", entries, str(output), 0, root=str(root)).paths
    assert sorted(path.name for path in output.iterdir()) == sorted(
        ["proj_combined.md", "other_combined_part9.md", "proj_combined_part1.md.bak"])
    assert [Path(path).name for path in single] == ["proj_combined.md"]


def test_base64_round_trips_a_non_ascii_name_and_a_file_dated_1975(make_project, tmp_path):
    root = make_project(tmp_path / "árvíztűrő projekt", {
        "main.py": "print('hello')\n", "old/legacy.c": "int main(void) { return 0; }\n"})
    dated_1975 = time.mktime((1975, 6, 1, 12, 0, 0, 0, 0, -1))
    os.utime(root / "old" / "legacy.c", (dated_1975, dated_1975))
    output = tmp_path / "out"
    output.mkdir()
    entries = _scan(root)
    result = core.write_base64_zip(core.project_name(root), entries, str(output), root=str(root))

    assert sorted(path.name for path in output.iterdir()) == ["árvíztűrő projekt_zip.b64.txt"]
    header = Path(result.paths[0]).read_text(encoding="utf-8").splitlines()[1]
    assert header == "# project name: árvíztűrő projekt"
    with _unzip(result.paths[0]) as archive:
        assert archive.namelist() == [f"árvíztűrő projekt/{e.relative_path}" for e in entries]
        for entry in entries:
            original = Path(long_path_safe(entry.full_path)).read_bytes()
            assert archive.read(f"árvíztűrő projekt/{entry.relative_path}") == original
        assert archive.getinfo("árvíztűrő projekt/old/legacy.c").date_time[0] == 1980


def test_a_file_that_disappears_before_the_build_is_logged_and_skipped(make_project, tmp_path):
    root = make_project(tmp_path / "proj", {"keep.py": "x = 1\n", "gone.py": "y = 2\n"})
    entries = _scan(root)
    (root / "gone.py").unlink()
    for write in (lambda log: core.write_markdown("proj", entries, str(tmp_path), log=log),
                  lambda log: core.write_base64_zip("proj", entries, str(tmp_path), log=log)):
        log = []
        result = write(log.append)
        assert (result.packed, result.errors) == (1, ["gone.py"])
        assert "skipped gone.py — the operating system refused to read it " \
               "[error.unreadable]" in log
    assert not list(tmp_path.glob("*.tmp"))


def test_the_size_estimates_are_close_on_the_fixture_tree(tmp_path):
    root = hostile_tree(tmp_path / "project", junctions=False)
    entries = _scan(root)
    md_estimate, b64_estimate = core.estimate_sizes(entries, "project")
    [md] = core.write_markdown("project", entries, str(tmp_path), root=str(root)).paths
    [b64] = core.write_base64_zip("project", entries, str(tmp_path), root=str(root)).paths
    assert md_estimate == pytest.approx(os.path.getsize(md), rel=0.05)
    assert b64_estimate == pytest.approx(os.path.getsize(b64), rel=0.03)

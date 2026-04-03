from __future__ import annotations

import pytest
from agent_clifs.commands.navigation import cmd_ls


class TestLs:
    def test_basic_listing(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["/"])
        assert "docs/" in result
        assert "src/" in result

    def test_long_format(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-l", "/src"])
        assert "tests/" in result
        assert "main.py" in result
        lines = result.strip().splitlines()
        for line in lines:
            assert line[0] in ("d", "f")

    def test_recursive(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-R", "/docs"])
        assert "/docs:" in result
        assert "/docs/api:" in result

    def test_ls_human_readable(self, populated_vfs):
        populated_vfs.write_file("/bigfile.txt", "x" * 2000)
        result = cmd_ls(populated_vfs, ["-lh", "/"])
        assert "2.0K" in result

    def test_ls_sort_by_size(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-lS", "/src"])
        lines = result.strip().splitlines()
        main_idx = next(i for i, l in enumerate(lines) if "main.py" in l)
        utils_idx = next(i for i, l in enumerate(lines) if "utils.py" in l)
        assert main_idx < utils_idx

    def test_ls_directory_flag(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-d", "/src"])
        assert "src/" in result
        assert "main.py" not in result
        assert "utils.py" not in result

    def test_ls_oneline_accepted(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-1", "/src"])
        assert "main.py" in result

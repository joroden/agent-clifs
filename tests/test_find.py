from __future__ import annotations

import pytest
from agent_clifs.commands.search import cmd_find
from agent_clifs.exceptions import CommandError


class TestFind:
    def test_find_all(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/"])
        assert "/docs" in result
        assert "/src" in result

    def test_find_name_glob(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-name", "*.py"])
        lines = result.strip().splitlines()
        assert "/src/main.py" in lines
        assert "/src/utils.py" in lines
        for line in lines:
            assert line.endswith(".py")

    def test_find_type_file(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f"])
        lines = result.strip().splitlines()
        for line in lines:
            assert populated_vfs.is_file(line)

    def test_find_type_dir(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "d"])
        lines = result.strip().splitlines()
        for line in lines:
            assert populated_vfs.is_dir(line)

    def test_find_path_pattern(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-path", "*/api/*"])
        lines = result.strip().splitlines()
        assert all("api" in l for l in lines)

    def test_find_maxdepth(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-maxdepth", "1"])
        lines = result.strip().splitlines()
        for line in lines:
            depth = line.count("/")
            assert depth <= 1

    def test_find_combined_filters(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-name", "*.md"])
        lines = result.strip().splitlines()
        for line in lines:
            assert line.endswith(".md")
            assert populated_vfs.is_file(line)

    def test_find_relative_start(self, populated_vfs):
        populated_vfs.chdir("/src")
        result = cmd_find(populated_vfs, [".", "-name", "*.py"])
        lines = result.strip().splitlines()
        assert any(l.startswith(".") for l in lines)

    def test_find_missing_dir_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="No such file"):
            cmd_find(populated_vfs, ["/nope"])

    def test_find_iname(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-iname", "README*"])
        lines = result.strip().splitlines()
        assert "/docs/readme.md" in lines

    def test_find_mindepth(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-mindepth", "2"])
        lines = result.strip().splitlines()
        assert "/" not in lines
        assert "/docs" not in lines
        assert "/src" not in lines
        assert any("readme.md" in l for l in lines)

    def test_find_not_name(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-not", "-name", "*.md"])
        lines = result.strip().splitlines()
        for line in lines:
            assert not line.endswith(".md")
        assert any(line.endswith(".py") for line in lines)

    def test_find_not_path(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-not", "-path", "*/docs/*"])
        lines = result.strip().splitlines()
        for line in lines:
            assert "/docs/" not in line
        assert any("src" in line for line in lines)

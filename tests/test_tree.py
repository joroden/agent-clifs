from __future__ import annotations

import pytest
from agent_clifs.commands.navigation import cmd_tree


class TestTree:
    def test_basic_structure(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["/"])
        assert "docs/" in result
        assert "src/" in result
        assert "directories" in result
        assert "files" in result

    def test_depth_limit(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-L", "1", "/"])
        assert "docs/" in result
        assert "readme.md" not in result

    def test_dirs_only(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["--dirs-only", "/"])
        assert "directories" in result
        assert "files" not in result
        assert "main.py" not in result

    def test_tree_d_flag(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-d", "/"])
        assert "directories" in result
        assert "files" not in result
        assert "main.py" not in result

    def test_tree_a_flag_accepted(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-a", "/"])
        assert "directories" in result

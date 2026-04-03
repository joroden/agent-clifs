from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_head


class TestHead:
    def test_default_lines(self, populated_vfs):
        result = cmd_head(populated_vfs, ["/src/main.py"])
        assert "def main():" in result

    def test_custom_lines(self, populated_vfs):
        result = cmd_head(populated_vfs, ["-n", "2", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) == 2

    def test_head_bytes(self, populated_vfs):
        result = cmd_head(populated_vfs, ["-c", "5", "/src/utils.py"])
        assert result == "def h"

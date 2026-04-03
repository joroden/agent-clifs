from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_tail


class TestTail:
    def test_default_lines(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["/src/main.py"])
        assert "main()" in result

    def test_custom_lines(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["-n", "2", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) == 2

    def test_tail_bytes(self, populated_vfs):
        content = populated_vfs.read_file("/src/utils.py")
        result = cmd_tail(populated_vfs, ["-c", "5", "/src/utils.py"])
        assert result == content[-5:]

    def test_tail_plus_n(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["-n", "+3", "/src/main.py"])
        assert "if __name__" in result
        assert "main()" in result
        assert "def main():" not in result
        assert "print('hello')" not in result

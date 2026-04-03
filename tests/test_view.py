from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_view
from agent_clifs.exceptions import CommandError


class TestView:
    def test_view_full_file(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py"])
        assert "File: /src/main.py (5 lines)" in result
        assert "1 | def main():" in result
        assert "5 |     main()" in result

    def test_view_line_range(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "2", "4"])
        assert "lines 2-4 of 5" in result
        assert "print('hello')" in result
        assert "def main():" not in result

    def test_view_start_only(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "3"])
        assert "lines 3-5 of 5" in result
        assert "main()" in result

    def test_view_header_shows_range(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "1", "3"])
        header = result.splitlines()[0]
        assert "lines 1-3 of 5" in header

    def test_view_beyond_end_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="beyond end"):
            cmd_view(populated_vfs, ["/src/main.py", "100"])

    def test_view_missing_file_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_view(populated_vfs, ["/nonexistent.py"])

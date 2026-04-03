from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_cat
from agent_clifs.exceptions import CommandError


class TestCat:
    def test_single_file(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["/src/utils.py"])
        assert "def helper():" in result

    def test_multiple_files(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["/src/utils.py", "/src/main.py"])
        assert "helper" in result
        assert "main" in result

    def test_numbering(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["-n", "/src/utils.py"])
        assert "1\t" in result
        assert "2\t" in result

    def test_missing_file_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_cat(populated_vfs, ["/nope.txt"])

    def test_cat_squeeze_blank(self, populated_vfs):
        populated_vfs.write_file("/blank.txt", "a\n\n\n\nb\n")
        result = cmd_cat(populated_vfs, ["-s", "/blank.txt"])
        assert result == "a\n\nb\n"

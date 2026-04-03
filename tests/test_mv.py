from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_mv
from agent_clifs.exceptions import CommandError


class TestMv:
    def test_mv_file(self, populated_vfs):
        cmd_mv(populated_vfs, ["/src/utils.py", "/src/helpers.py"])
        assert populated_vfs.is_file("/src/helpers.py")
        assert not populated_vfs.exists("/src/utils.py")

    def test_mv_directory(self, populated_vfs):
        cmd_mv(populated_vfs, ["/docs", "/documentation"])
        assert populated_vfs.is_dir("/documentation")
        assert populated_vfs.is_file("/documentation/readme.md")
        assert not populated_vfs.exists("/docs")

    def test_mv_missing_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_mv(populated_vfs, ["/nope", "/dest"])

    def test_mv_force_accepted(self, populated_vfs):
        cmd_mv(populated_vfs, ["-f", "/src/utils.py", "/src/helpers.py"])
        assert populated_vfs.is_file("/src/helpers.py")

    def test_mv_no_clobber(self, populated_vfs):
        populated_vfs.write_file("/a.txt", "aaa")
        populated_vfs.write_file("/b.txt", "bbb")
        cmd_mv(populated_vfs, ["-n", "/a.txt", "/b.txt"])
        assert populated_vfs.read_file("/b.txt") == "bbb"
        assert populated_vfs.is_file("/a.txt")

    def test_mv_verbose(self, populated_vfs):
        result = cmd_mv(populated_vfs, ["-v", "/src/utils.py", "/src/helpers.py"])
        assert "renamed" in result
        assert "->" in result

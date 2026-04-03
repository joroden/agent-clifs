from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_mkdir
from agent_clifs.exceptions import CommandError


class TestMkdirCmd:
    def test_mkdir(self, vfs):
        cmd_mkdir(vfs, ["/newdir"])
        assert vfs.is_dir("/newdir")

    def test_mkdir_parents(self, vfs):
        cmd_mkdir(vfs, ["-p", "/a/b/c"])
        assert vfs.is_dir("/a/b/c")

    def test_mkdir_existing_raises(self, vfs):
        vfs.mkdir("/dup")
        with pytest.raises(CommandError):
            cmd_mkdir(vfs, ["/dup"])

    def test_mkdir_verbose(self, populated_vfs):
        result = cmd_mkdir(populated_vfs, ["-v", "/newdir"])
        assert "created directory" in result

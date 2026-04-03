from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_append
from agent_clifs.exceptions import CommandError


class TestAppendCmd:
    def test_creates_then_appends(self, vfs):
        cmd_append(vfs, ["/log.txt", "first"])
        cmd_append(vfs, ["/log.txt", " second"])
        assert vfs.read_file("/log.txt") == "first second"

    def test_no_args_raises(self, vfs):
        with pytest.raises(CommandError):
            cmd_append(vfs, [])

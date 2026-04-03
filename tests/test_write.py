from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_write
from agent_clifs.exceptions import CommandError


class TestWrite:
    def test_creates_file_with_content(self, vfs):
        cmd_write(vfs, ["/f.txt", "hello", "world"])
        assert vfs.read_file("/f.txt") == "hello world"

    def test_no_args_raises(self, vfs):
        with pytest.raises(CommandError):
            cmd_write(vfs, [])

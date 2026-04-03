from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_touch


class TestTouch:
    def test_creates_file(self, vfs):
        cmd_touch(vfs, ["/new.txt"])
        assert vfs.is_file("/new.txt")
        assert vfs.read_file("/new.txt") == ""

    def test_existing_is_noop(self, vfs):
        vfs.write_file("/exist.txt", "data")
        cmd_touch(vfs, ["/exist.txt"])
        assert vfs.read_file("/exist.txt") == "data"

    def test_touch_no_create(self, populated_vfs):
        cmd_touch(populated_vfs, ["-c", "/nonexistent.txt"])
        assert not populated_vfs.exists("/nonexistent.txt")

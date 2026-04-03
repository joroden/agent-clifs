from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_rm
from agent_clifs.exceptions import CommandError


class TestRm:
    def test_rm_file(self, populated_vfs):
        cmd_rm(populated_vfs, ["/src/utils.py"])
        assert not populated_vfs.exists("/src/utils.py")

    def test_rm_dir_recursive(self, populated_vfs):
        cmd_rm(populated_vfs, ["-r", "/docs"])
        assert not populated_vfs.exists("/docs")

    def test_rm_dir_without_r_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="Is a directory"):
            cmd_rm(populated_vfs, ["/docs"])

    def test_rm_force_missing_silent(self, populated_vfs):
        cmd_rm(populated_vfs, ["-f", "/nope.txt"])

    def test_rm_verbose(self, populated_vfs):
        result = cmd_rm(populated_vfs, ["-v", "/src/utils.py"])
        assert "removed" in result
        assert "/src/utils.py" in result

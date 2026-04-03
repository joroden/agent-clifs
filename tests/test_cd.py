from __future__ import annotations

import pytest
from agent_clifs.commands.navigation import cmd_cd
from agent_clifs.exceptions import CommandError


class TestCd:
    def test_cd_changes_dir(self, populated_vfs):
        cmd_cd(populated_vfs, ["/src"])
        assert populated_vfs.cwd == "/src"

    def test_cd_no_args_goes_to_root(self, populated_vfs):
        populated_vfs.chdir("/docs")
        cmd_cd(populated_vfs, [])
        assert populated_vfs.cwd == "/"

    def test_cd_missing_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_cd(populated_vfs, ["/nope"])

    def test_cd_tilde_goes_to_root(self, populated_vfs):
        cmd_cd(populated_vfs, ["/docs"])
        cmd_cd(populated_vfs, ["~"])
        assert populated_vfs.cwd == "/"

    def test_cd_dash_goes_to_previous(self, populated_vfs):
        cmd_cd(populated_vfs, ["/docs"])
        cmd_cd(populated_vfs, ["-"])
        assert populated_vfs.cwd == "/"

    def test_cd_dash_no_previous_raises(self, populated_vfs):
        from agent_clifs.commands.navigation import _previous_dirs
        _previous_dirs.pop(id(populated_vfs), None)
        with pytest.raises(CommandError, match="no previous directory"):
            cmd_cd(populated_vfs, ["-"])

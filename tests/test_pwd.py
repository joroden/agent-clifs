from __future__ import annotations

import pytest
from agent_clifs.commands.navigation import cmd_pwd


class TestPwd:
    def test_returns_cwd(self, populated_vfs):
        assert cmd_pwd(populated_vfs, []) == "/"

    def test_after_chdir(self, populated_vfs):
        populated_vfs.chdir("/docs")
        assert cmd_pwd(populated_vfs, []) == "/docs"

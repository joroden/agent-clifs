from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import cmd_cp
from agent_clifs.exceptions import CommandError


class TestCp:
    def test_cp_file(self, populated_vfs):
        cmd_cp(populated_vfs, ["/src/utils.py", "/src/utils_copy.py"])
        assert populated_vfs.read_file("/src/utils_copy.py") == populated_vfs.read_file("/src/utils.py")

    def test_cp_recursive_dir(self, populated_vfs):
        cmd_cp(populated_vfs, ["-r", "/docs", "/docs_backup"])
        assert populated_vfs.is_file("/docs_backup/readme.md")
        assert populated_vfs.is_dir("/docs_backup/api")

    def test_cp_dir_without_r_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="not specified"):
            cmd_cp(populated_vfs, ["/docs", "/docs2"])

    def test_cp_archive(self, populated_vfs):
        cmd_cp(populated_vfs, ["-a", "/docs", "/docs_copy"])
        assert populated_vfs.is_file("/docs_copy/readme.md")
        assert populated_vfs.is_dir("/docs_copy/api")

    def test_cp_no_clobber(self, populated_vfs):
        populated_vfs.write_file("/orig.txt", "original")
        populated_vfs.write_file("/copy.txt", "existing")
        cmd_cp(populated_vfs, ["-n", "/orig.txt", "/copy.txt"])
        assert populated_vfs.read_file("/copy.txt") == "existing"

    def test_cp_verbose(self, populated_vfs):
        result = cmd_cp(populated_vfs, ["-v", "/src/utils.py", "/src/utils_backup.py"])
        assert "'" in result
        assert "->" in result

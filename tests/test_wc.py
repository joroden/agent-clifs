from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_wc


class TestWc:
    def test_all_counts(self, populated_vfs):
        result = cmd_wc(populated_vfs, ["/src/utils.py"])
        assert "utils.py" in result

    def test_lines_only(self, populated_vfs):
        result = cmd_wc(populated_vfs, ["-l", "/src/utils.py"])
        assert "utils.py" in result
        parts = result.strip().split()
        assert len(parts) == 2

    def test_words_only(self, populated_vfs):
        result = cmd_wc(populated_vfs, ["-w", "/src/utils.py"])
        parts = result.strip().split()
        assert len(parts) == 2

    def test_bytes_only(self, populated_vfs):
        result = cmd_wc(populated_vfs, ["-c", "/src/utils.py"])
        parts = result.strip().split()
        assert len(parts) == 2

    def test_multiple_files_totals(self, populated_vfs):
        result = cmd_wc(populated_vfs, ["/src/utils.py", "/src/main.py"])
        assert "total" in result

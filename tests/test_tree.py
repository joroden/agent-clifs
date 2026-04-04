from __future__ import annotations

import pytest
from agent_clifs.commands.navigation import cmd_tree


class TestTree:
    def test_basic_structure(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["/"])
        assert "docs/" in result
        assert "src/" in result
        assert "directories" in result
        assert "files" in result

    def test_depth_limit(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-L", "1", "/"])
        assert "docs/" in result
        assert "readme.md" not in result

    def test_dirs_only(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["--dirs-only", "/"])
        assert "directories" in result
        assert "files" not in result
        assert "main.py" not in result

    def test_tree_d_flag(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-d", "/"])
        assert "directories" in result
        assert "files" not in result
        assert "main.py" not in result

    def test_tree_a_flag_accepted(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-a", "/"])
        assert "directories" in result


class TestTreeLLMFormat:
    """Tests for LLM-optimised tree output via LLMFormatter."""

    def _fmt(self, populated_vfs, args=None):
        from agent_clifs import AgentCLI
        cli = AgentCLI(populated_vfs, structured={"tree"})
        return cli.execute("tree " + " ".join(args or ["/"]))

    def test_full_absolute_paths_files(self, populated_vfs):
        result = self._fmt(populated_vfs)
        assert "[file] /docs/readme.md" in result
        assert "[file] /src/main.py" in result

    def test_full_absolute_paths_dirs(self, populated_vfs):
        result = self._fmt(populated_vfs)
        assert "[dir] /docs" in result
        assert "[dir] /src" in result

    def test_no_box_drawing_chars(self, populated_vfs):
        result = self._fmt(populated_vfs)
        assert "├" not in result
        assert "└" not in result
        assert "│" not in result

    def test_no_indentation(self, populated_vfs):
        result = self._fmt(populated_vfs)
        # every line is either [dir] or [file] or the summary
        for line in result.splitlines():
            if line.startswith("("):
                continue
            assert line.startswith("[dir] ") or line.startswith("[file] "), repr(line)

    def test_sorted_parents_before_children(self, populated_vfs):
        result = self._fmt(populated_vfs)
        lines = [l for l in result.splitlines() if l.startswith("[")]
        paths = [l.split("] ", 1)[1].split("  (")[0] for l in lines]
        assert paths == sorted(paths)

    def test_includes_line_counts(self, populated_vfs):
        result = self._fmt(populated_vfs)
        # At least one file should have a line count annotation
        assert "lines)" in result or "line)" in result

    def test_summary_present(self, populated_vfs):
        result = self._fmt(populated_vfs)
        assert result.strip().endswith(")")
        assert "files" in result or "file" in result

    def test_depth_limit_respected(self, populated_vfs):
        result = self._fmt(populated_vfs, ["-L", "1", "/"])
        # Subdirectory contents should not appear
        assert "readme.md" not in result
        assert "[dir] /docs" in result

    def test_dirs_only_no_files(self, populated_vfs):
        result = self._fmt(populated_vfs, ["-d", "/"])
        assert "[file]" not in result
        assert "[dir]" in result

    def test_subtree_path(self, populated_vfs):
        result = self._fmt(populated_vfs, ["/src"])
        assert "[file] /src/main.py" in result
        assert "docs" not in result

"""Tests for pipe (|) support in AgentCLI."""

from __future__ import annotations

import pytest

from agent_clifs.cli import AgentCLI
from agent_clifs.exceptions import CommandError
from agent_clifs.vfs import VirtualFileSystem


@pytest.fixture
def vfs():
    return VirtualFileSystem()


class TestPipes:
    """Functional tests for pipeline execution."""

    def test_simple_pipe(self, vfs):
        vfs.write_file("/f.txt", "alpha\nbeta\ngamma\nalpha two")
        cli = AgentCLI(vfs)
        result = cli.execute("cat /f.txt | grep alpha")
        assert "alpha" in result
        assert "beta" not in result

    def test_multi_pipe(self, vfs):
        vfs.write_file("/f.txt", "a\nb\nc\nd\ne\n")
        cli = AgentCLI(vfs)
        result = cli.execute("cat /f.txt | grep -v c | wc -l")
        # 4 lines remaining after filtering out 'c'
        assert "4" in result

    def test_pipe_with_head(self, vfs):
        lines = "\n".join(str(i) for i in range(1, 21))
        vfs.write_file("/nums.txt", lines)
        cli = AgentCLI(vfs)
        result = cli.execute("cat /nums.txt | head -n 5")
        result_lines = result.strip().splitlines()
        assert len(result_lines) == 5
        assert result_lines[0] == "1"
        assert result_lines[4] == "5"

    def test_pipe_with_tail(self, vfs):
        lines = "\n".join(str(i) for i in range(1, 11))
        vfs.write_file("/nums.txt", lines)
        cli = AgentCLI(vfs)
        result = cli.execute("cat /nums.txt | tail -n 3")
        result_lines = result.strip().splitlines()
        assert len(result_lines) == 3
        assert result_lines[-1] == "10"

    def test_pipe_with_wc(self, vfs):
        vfs.mkdir("/d")
        vfs.write_file("/d/a.txt", "")
        vfs.write_file("/d/b.txt", "")
        vfs.write_file("/d/c.txt", "")
        cli = AgentCLI(vfs)
        result = cli.execute("ls /d | wc -l")
        assert "3" in result

    def test_pipe_preserves_quotes(self, vfs):
        vfs.write_file("/f.txt", "hello world\nhello there\ngoodbye world")
        cli = AgentCLI(vfs)
        # The | outside quotes is a pipe; the quoted "hello" is preserved
        result = cli.execute('grep "hello" /f.txt | wc -l')
        assert "2" in result

    def test_empty_pipe_segment_raises(self, vfs):
        vfs.write_file("/f.txt", "x")
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError, match="empty command between pipes"):
            cli.execute("cat /f.txt | | grep x")

    def test_leading_pipe_raises(self, vfs):
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError, match="unexpected '|' at start"):
            cli.execute("| grep x")

    def test_trailing_pipe_raises(self, vfs):
        vfs.write_file("/f.txt", "x")
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError, match="unexpected '|' at end"):
            cli.execute("cat /f.txt |")

    def test_pipe_temp_files_cleaned_up(self, vfs):
        vfs.write_file("/f.txt", "hello\nworld")
        cli = AgentCLI(vfs)
        cli.execute("cat /f.txt | grep hello")
        # No /tmp/.pipe_* files should remain
        if vfs.is_dir("/tmp"):
            for entry in vfs.list_dir("/tmp"):
                assert not entry.startswith(".pipe_")

    def test_pipe_error_propagation(self, vfs):
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError):
            cli.execute("cat /nonexistent.txt | grep hello")

    def test_pipe_error_in_middle(self, vfs):
        vfs.write_file("/f.txt", "hello")
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError):
            cli.execute("cat /f.txt | nonexistent_cmd | grep hello")
        # Temp files should still be cleaned up
        if vfs.is_dir("/tmp"):
            for entry in vfs.list_dir("/tmp"):
                assert not entry.startswith(".pipe_")

    def test_pipe_with_find(self, vfs):
        vfs.write_file("/src/test_a.py", "")
        vfs.write_file("/src/test_b.py", "")
        vfs.write_file("/src/main.py", "")
        cli = AgentCLI(vfs)
        result = cli.execute("find /src -name '*.py' | grep test")
        assert "test_a.py" in result
        assert "test_b.py" in result
        assert "main.py" not in result

    def test_pipe_quoted_bar_not_split(self, vfs):
        vfs.write_file("/f.txt", "a|b\nc|d\nef")
        cli = AgentCLI(vfs)
        # The | inside double quotes is literal, not a pipe
        result = cli.execute('grep "a|b" /f.txt')
        assert "a|b" in result

    def test_pipe_single_quoted_bar_not_split(self, vfs):
        vfs.write_file("/f.txt", "a|b\nc|d\nef")
        cli = AgentCLI(vfs)
        # The | inside single quotes is literal, not a pipe
        result = cli.execute("grep 'a|b' /f.txt")
        assert "a|b" in result


class TestPipeSecurity:
    """Security-related pipe tests."""

    def test_pipe_no_temp_file_leak_on_error(self, vfs):
        vfs.write_file("/f.txt", "data")
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError):
            cli.execute("cat /f.txt | cat /nonexistent")
        if vfs.is_dir("/tmp"):
            for entry in vfs.list_dir("/tmp"):
                assert not entry.startswith(".pipe_")

    def test_pipe_temp_file_not_accessible_after(self, vfs):
        vfs.write_file("/f.txt", "secret data")
        cli = AgentCLI(vfs)
        cli.execute("cat /f.txt | grep secret")
        # No temp files should be accessible
        if vfs.is_dir("/tmp"):
            entries = vfs.list_dir("/tmp")
            pipe_files = [e for e in entries if e.startswith(".pipe_")]
            assert pipe_files == []

    def test_pipe_with_path_traversal(self, vfs):
        vfs.write_file("/f.txt", "safe data")
        cli = AgentCLI(vfs)
        # Even through pipes, path traversal should be contained
        result = cli.execute("cat /f.txt | grep safe")
        assert "safe data" in result

"""Tests for output redirection (>, >>, /dev/null, 2>, 2>>)."""

from __future__ import annotations

import pytest

from agent_clifs import AgentCLI, VirtualFileSystem
from agent_clifs.exceptions import CommandError


@pytest.fixture
def vfs():
    return VirtualFileSystem()


@pytest.fixture
def cli(vfs):
    return AgentCLI(vfs)


@pytest.fixture
def readonly_cli(vfs):
    return AgentCLI(vfs, readonly=True)


# ── TestOutputRedirection ─────────────────────────────────────────────


class TestOutputRedirection:
    def test_redirect_overwrite(self, cli, vfs):
        cli.execute("mkdir /docs")
        cli.execute("ls / > /output.txt")
        assert "docs" in vfs.read_file("/output.txt")

    def test_redirect_append(self, cli, vfs):
        vfs.write_file("/log.txt", "line1\n")
        cli.execute("pwd >> /log.txt")
        content = vfs.read_file("/log.txt")
        assert content.startswith("line1\n")
        assert "/" in content

    def test_redirect_dev_null(self, cli):
        result = cli.execute("ls / > /dev/null")
        assert result == ""

    def test_redirect_dev_null_append(self, cli):
        result = cli.execute("ls / >> /dev/null")
        assert result == ""

    def test_redirect_returns_empty(self, cli, vfs):
        result = cli.execute("pwd > /out.txt")
        assert result == ""

    def test_redirect_creates_file(self, cli, vfs):
        cli.execute("pwd > /new_output.txt")
        assert vfs.exists("/new_output.txt")

    def test_redirect_overwrites_existing(self, cli, vfs):
        vfs.write_file("/out.txt", "old content")
        cli.execute("pwd > /out.txt")
        assert vfs.read_file("/out.txt") != "old content"

    def test_redirect_appends_existing(self, cli, vfs):
        vfs.write_file("/out.txt", "AAA")
        cli.execute("pwd >> /out.txt")
        content = vfs.read_file("/out.txt")
        assert content.startswith("AAA")
        assert len(content) > 3

    def test_redirect_no_space(self, cli):
        result = cli.execute("ls />/dev/null")
        assert result == ""

    def test_redirect_with_pipe(self, cli, vfs):
        vfs.write_file("/data.txt", "hello world\nfoo bar\nhello again\n")
        cli.execute("cat /data.txt | grep hello > /output.txt")
        content = vfs.read_file("/output.txt")
        assert "hello" in content

    def test_redirect_only_last_pipe(self, cli, vfs):
        vfs.write_file("/data.txt", "alpha\nbeta\ngamma\n")
        cli.execute("cat /data.txt | grep alpha > /result.txt")
        content = vfs.read_file("/result.txt")
        assert "alpha" in content
        assert "beta" not in content


# ── TestStderrRedirection ─────────────────────────────────────────────


class TestStderrRedirection:
    def test_stderr_redirect_noop(self, cli, vfs):
        vfs.write_file("/file.txt", "data")
        result = cli.execute("ls / 2> /dev/null")
        # Command runs normally; stderr redirect is silently ignored
        assert result != ""

    def test_stderr_redirect_file_noop(self, cli, vfs):
        vfs.write_file("/file.txt", "data")
        cli.execute("ls / 2> /stderr_output.txt")
        assert not vfs.exists("/stderr_output.txt")

    def test_stderr_append_noop(self, cli, vfs):
        vfs.write_file("/file.txt", "data")
        result = cli.execute("ls / 2>> /dev/null")
        assert result != ""


# ── TestRedirectionParsing ────────────────────────────────────────────


class TestRedirectionParsing:
    def test_quoted_gt_not_redirect(self, cli, vfs):
        vfs.write_file("/data.txt", "a > b\nfoo\n")
        result = cli.execute('grep ">" /data.txt')
        assert "a > b" in result

    def test_single_quoted_gt_not_redirect(self, cli, vfs):
        vfs.write_file("/data.txt", "a > b\nfoo\n")
        result = cli.execute("grep '>' /data.txt")
        assert "a > b" in result

    def test_gt_in_file_content_not_redirect(self, cli, vfs):
        cli.execute('write /f.txt "a > b"')
        content = vfs.read_file("/f.txt")
        assert "a > b" in content

    def test_multiple_redirects_last_wins(self, cli, vfs):
        cli.execute("pwd > /a.txt > /b.txt")
        assert vfs.exists("/b.txt")
        assert "/" in vfs.read_file("/b.txt")


# ── TestRedirectionSecurity ───────────────────────────────────────────


class TestRedirectionSecurity:
    def test_redirect_path_traversal(self, cli, vfs):
        # Path traversal is normalized by VFS resolve_path
        cli.execute("pwd > /../../../../etc/passwd")
        assert vfs.exists("/etc/passwd")
        assert "/" in vfs.read_file("/etc/passwd")

    def test_redirect_readonly_blocks_file_redirect(self, readonly_cli):
        with pytest.raises(CommandError, match="readonly"):
            readonly_cli.execute("pwd > /out.txt")

    def test_redirect_readonly_allows_dev_null(self, readonly_cli):
        result = readonly_cli.execute("pwd > /dev/null")
        assert result == ""

    def test_redirect_temp_files_no_leak(self, cli, vfs):
        vfs.write_file("/data.txt", "hello\nworld\n")
        cli.execute("cat /data.txt | grep hello > /result.txt")
        # Verify no leftover temp files in /tmp
        for path in list(vfs._files):
            assert not path.startswith("/tmp/.pipe_"), f"leaked temp file: {path}"


# ── TestRedirectionEdgeCases ──────────────────────────────────────────


class TestRedirectionEdgeCases:
    def test_redirect_empty_output(self, cli, vfs):
        cli.execute("touch /f")
        cli.execute("touch /f > /out.txt")
        assert vfs.read_file("/out.txt") == ""

    def test_redirect_missing_target(self, cli):
        with pytest.raises(CommandError, match="missing redirect target"):
            cli.execute("ls / >")

    def test_redirect_to_directory_raises(self, cli, vfs):
        cli.execute("mkdir /existing_dir")
        with pytest.raises(CommandError):
            cli.execute("ls / > /existing_dir")

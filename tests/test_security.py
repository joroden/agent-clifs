"""Security-oriented tests for agent-clifs."""

from __future__ import annotations

import os
import uuid

import pytest

from agent_clifs import AgentCLI, VirtualFileSystem
from agent_clifs.commands.grep import cmd_grep
from agent_clifs.exceptions import CommandError, VFSError


@pytest.fixture
def vfs():
    return VirtualFileSystem()


@pytest.fixture
def cli(vfs):
    return AgentCLI(vfs)


# ------------------------------------------------------------------
# ReDoS (Regular Expression Denial of Service)
# ------------------------------------------------------------------

class TestReDoS:
    """grep statically rejects patterns with nested quantifiers."""

    @pytest.fixture
    def populated_vfs(self):
        fs = VirtualFileSystem()
        fs.write_file("/test.txt", "hello world\nfoo bar\nbaz")
        return fs

    def test_nested_quantifier_rejected(self, populated_vfs):
        """(a+)+$ contains nested quantifiers and must be rejected immediately."""
        with pytest.raises(CommandError, match="nested quantifiers"):
            cmd_grep(populated_vfs, ["(a+)+$", "/test.txt"])

    def test_alternation_nested_quantifier_rejected(self, populated_vfs):
        """(a|a?)+ contains nested quantifiers (? inside a quantified group)."""
        with pytest.raises(CommandError, match="nested quantifiers"):
            cmd_grep(populated_vfs, ["(a|a?)+$", "/test.txt"])

    def test_star_nested_quantifier_rejected(self, populated_vfs):
        """(a*)+ is another classic ReDoS form and must be rejected."""
        with pytest.raises(CommandError, match="nested quantifiers"):
            cmd_grep(populated_vfs, ["(a*)+", "/test.txt"])

    def test_normal_pattern_completes(self, populated_vfs):
        """A well-formed pattern without nested quantifiers works fine."""
        result = cmd_grep(populated_vfs, ["hello", "/test.txt"])
        assert "hello" in result

    def test_fixed_strings_bypasses_check(self, populated_vfs):
        """-F escapes the pattern before the ReDoS check — always safe."""
        result = cmd_grep(populated_vfs, ["-F", "(a+)+$", "/test.txt"])
        assert result == ""

    def test_invalid_regex_raises_command_error(self, populated_vfs):
        """Malformed regex raises CommandError, not an unhandled exception."""
        with pytest.raises(CommandError, match="invalid regex"):
            cmd_grep(populated_vfs, ["[unclosed", "/test.txt"])

    def test_long_literal_pattern_does_not_hang(self, vfs):
        """A very long literal pattern string completes without issue."""
        vfs.write_file("/test.txt", "hello world")
        result = cmd_grep(vfs, ["a" * 5000, "/test.txt"])
        assert result == ""


# ------------------------------------------------------------------
# Path traversal
# ------------------------------------------------------------------

class TestPathTraversal:
    """Traversal attempts cannot escape the VFS root."""

    def test_dotdot_clamps_to_vfs_root(self, vfs):
        """../../../../etc/passwd resolves within the VFS, not the real FS."""
        assert vfs.resolve_path("/../../../../etc/passwd") == "/etc/passwd"

    def test_traversal_read_stays_in_vfs(self, vfs):
        """cat with traversal path reads from VFS, not the real filesystem."""
        cli = AgentCLI(vfs)
        # /etc/passwd doesn't exist in the VFS
        with pytest.raises(CommandError):
            cli.execute("cat /../../../../etc/passwd")

    def test_traversal_write_stays_in_vfs(self, vfs):
        """write with traversal path writes into the VFS, never to disk."""
        unique = f"/tmp/agent_clifs_{uuid.uuid4().hex}.txt"
        cli = AgentCLI(vfs)
        # Path resolves to /tmp/<unique> inside the VFS
        cli.execute(f"write /../../../../{unique.lstrip('/')} malicious")
        assert vfs.is_file(unique)
        assert not os.path.exists(unique)

    def test_traversal_grep_stays_in_vfs(self, vfs):
        """grep with traversal path never touches the real filesystem."""
        vfs.write_file("/docs/file.txt", "content")
        cli = AgentCLI(vfs)
        # Should search the VFS copy of /etc, not the real /etc
        result = cli.execute("grep -r content /../../../../docs")
        assert "content" in result

    def test_relative_traversal_clamps(self, vfs):
        """Relative ../ beyond root stays at root."""
        vfs.chdir("/some/deep/path" if vfs.is_dir("/some/deep/path") else "/")
        assert vfs.resolve_path("../../../../../../../etc") == "/etc"


# ------------------------------------------------------------------
# Command injection via execute()
# ------------------------------------------------------------------

class TestCommandInjection:
    """shlex parsing prevents shell metacharacters from being interpreted."""

    def test_semicolon_not_command_separator(self, vfs):
        """ls /a; rm -rf / treats ';' as part of a path arg, not a separator."""
        vfs.write_file("/important.txt", "keep this")
        cli = AgentCLI(vfs)
        try:
            cli.execute("ls /nonexistent; rm -rf /")
        except CommandError:
            pass  # expected — /nonexistent; doesn't exist
        # The VFS must be untouched
        assert vfs.is_file("/important.txt")

    def test_pipe_works_as_pipeline(self, vfs):
        """| is treated as a pipe operator."""
        vfs.write_file("/test.txt", "hello world\nfoo bar\nbaz hello")
        cli = AgentCLI(vfs)
        result = cli.execute("cat /test.txt | grep hello")
        assert "hello world" in result
        assert "baz hello" in result
        assert "foo bar" not in result

    def test_ampersand_not_background_operator(self, vfs):
        """&& is not treated as a logical AND shell operator."""
        vfs.write_file("/a.txt", "a")
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError):
            cli.execute("ls /a.txt && ls /a.txt")

    def test_subshell_not_executed(self, vfs):
        """$(...) and backticks are not evaluated — shlex treats them literally."""
        cli = AgentCLI(vfs)
        with pytest.raises(CommandError):
            cli.execute("cat $(echo /etc/passwd)")

    def test_unclosed_quote_raises_command_error(self, cli):
        """Malformed quoting raises CommandError, not a Python exception."""
        with pytest.raises(CommandError, match="syntax error"):
            cli.execute("cat 'unclosed")


# ------------------------------------------------------------------
# Null bytes and unusual input
# ------------------------------------------------------------------

class TestNullBytesAndEdgeCases:
    """Unusual input is handled gracefully."""

    def test_null_byte_in_path_raises_cleanly(self, cli):
        """A null byte in a path produces a CommandError, not a crash."""
        with pytest.raises((CommandError, VFSError)):
            cli.execute("cat /foo\x00bar")

    def test_null_byte_in_content_is_stored(self, vfs):
        """Null bytes in file content are stored as-is (VFS is pure Python)."""
        cli = AgentCLI(vfs)
        vfs.write_file("/binary.bin", "before\x00after")
        result = cli.execute("cat /binary.bin")
        assert "\x00" in result

    def test_very_long_path_raises_cleanly(self, cli):
        """An absurdly long path doesn't crash — it just isn't found."""
        long_path = "/a" * 1000
        with pytest.raises((CommandError, VFSError)):
            cli.execute(f"cat {long_path}")

    def test_empty_execute_returns_empty(self, cli):
        """Calling execute with an empty string returns empty string."""
        assert cli.execute("") == ""

    def test_whitespace_only_execute_returns_empty(self, cli):
        """Whitespace-only command returns empty string."""
        assert cli.execute("   ") == ""

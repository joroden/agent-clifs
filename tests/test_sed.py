from __future__ import annotations

import pytest
from agent_clifs.commands.read import cmd_sed
from agent_clifs.exceptions import CommandError


CONTENT = "\n".join(f"line{i}" for i in range(1, 11))  # line1..line10


class TestSed:
    def test_print_line_range(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "1,3p", "/f.txt"])
        assert result == "line1\nline2\nline3"

    def test_print_single_line(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "5p", "/f.txt"])
        assert result == "line5"

    def test_print_to_end(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "8,$p", "/f.txt"])
        assert result == "line8\nline9\nline10"

    def test_print_last_line(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "$p", "/f.txt"])
        assert result == "line10"

    def test_print_pattern(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "/line[13]$/p", "/f.txt"])
        assert result == "line1\nline3"

    def test_print_pattern_range(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "/line3/,/line5/p", "/f.txt"])
        assert result == "line3\nline4\nline5"

    def test_unsupported_command_raises(self, vfs):
        vfs.write_file("/f.txt", "a\nb\nc\n")
        with pytest.raises(CommandError, match="unsupported command"):
            cmd_sed(vfs, ["s/x/y/", "/f.txt"])

    def test_no_n_prints_all_lines(self, vfs):
        vfs.write_file("/f.txt", "a\nb\nc")
        result = cmd_sed(vfs, ["1,2d", "/f.txt"])
        assert result == "c"

    def test_delete_range(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["3,7d", "/f.txt"])
        lines = result.splitlines()
        assert "line3" not in lines
        assert "line7" not in lines
        assert "line1" in lines
        assert "line10" in lines

    def test_quit_stops_at_line(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["5q", "/f.txt"])
        lines = result.splitlines()
        assert lines[-1] == "line5"
        assert "line6" not in lines

    def test_print_line_number(self, vfs):
        vfs.write_file("/f.txt", "a\nb\nc")
        result = cmd_sed(vfs, ["-n", "2=", "/f.txt"])
        assert result == "2"

    def test_multiple_expressions(self, vfs):
        vfs.write_file("/f.txt", CONTENT)
        result = cmd_sed(vfs, ["-n", "-e", "2p", "-e", "4p", "/f.txt"])
        assert result == "line2\nline4"

    def test_no_script_raises(self, vfs):
        with pytest.raises(CommandError, match="no script"):
            cmd_sed(vfs, [])

    def test_no_file_raises(self, vfs):
        with pytest.raises(CommandError, match="no input file"):
            cmd_sed(vfs, ["1p"])

    def test_missing_file_raises(self, vfs):
        with pytest.raises(CommandError):
            cmd_sed(vfs, ["-n", "1p", "/nonexistent.txt"])

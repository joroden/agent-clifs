from __future__ import annotations

import pytest
from agent_clifs.commands.grep import cmd_grep
from agent_clifs.exceptions import CommandError


class TestGrep:
    def test_basic_match(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["def", "/src/main.py"])
        assert "def main():" in result

    def test_case_insensitive(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-i", "DEF", "/src/main.py"])
        assert "def main():" in result

    def test_line_numbers(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-n", "def", "/src/main.py"])
        assert "1:" in result

    def test_recursive(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "def", "/src"])
        assert "main.py" in result
        assert "utils.py" in result

    def test_files_only(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-rl", "def", "/src"])
        lines = result.strip().splitlines()
        assert "/src/main.py" in lines
        assert "/src/utils.py" in lines

    def test_count(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-c", "def", "/src/main.py"])
        assert result.strip() == "1"

    def test_invert_match(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-v", "def", "/src/utils.py"])
        assert "def helper" not in result
        assert "return 42" in result

    def test_word_match(self, populated_vfs):
        populated_vfs.write_file("/words.txt", "cat\ncatch\nthe cat sat\n")
        result = cmd_grep(populated_vfs, ["-w", "cat", "/words.txt"])
        lines = result.strip().splitlines()
        assert "cat" in lines
        assert "the cat sat" in lines
        assert "catch" not in lines

    def test_after_context(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-A", "1", "def main", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) >= 2
        assert "def main():" in lines[0]

    def test_before_context(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-B", "1", "print", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) >= 2

    def test_context_combined(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-C", "1", "print", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) >= 2

    def test_no_matches_empty(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["zzzzz_no_match", "/src/main.py"])
        assert result == ""

    def test_invalid_regex_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="invalid regex"):
            cmd_grep(populated_vfs, ["[invalid", "/src/main.py"])

    def test_directory_without_r_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="Is a directory"):
            cmd_grep(populated_vfs, ["pattern", "/src"])

    def test_count_with_multiple_files(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-rc", "def", "/src"])
        assert "/src/main.py:" in result
        assert "/src/utils.py:" in result

    def test_missing_file_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="No such file"):
            cmd_grep(populated_vfs, ["pat", "/nonexistent.txt"])

    def test_grep_fixed_strings(self, populated_vfs):
        populated_vfs.write_file("/meta.txt", "a.b\na*b\naxb\nnormal\n")
        result = cmd_grep(populated_vfs, ["-F", "a.b", "/meta.txt"])
        lines = result.strip().splitlines()
        assert "a.b" in lines
        assert "axb" not in lines

    def test_grep_multiple_patterns(self, populated_vfs):
        result = cmd_grep(populated_vfs, [
            "-e", "def", "-e", "return",
            "/src/utils.py",
        ])
        assert "def helper():" in result
        assert "return 42" in result

    def test_grep_with_filename(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-H", "def", "/src/main.py"])
        assert "/src/main.py:" in result

    def test_grep_no_filename(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-rh", "def", "/src"])
        assert "/src/" not in result
        assert "def" in result

    def test_grep_include(self, populated_vfs):
        populated_vfs.write_file("/src/notes.txt", "def some stuff\n")
        result = cmd_grep(populated_vfs, ["-r", "--include=*.py", "def", "/src"])
        assert "main.py" in result
        assert "notes.txt" not in result

    def test_grep_exclude(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "--exclude=*.md", "API", "/docs"])
        assert result == ""

    def test_y_flag_is_ignore_case_alias(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-y", "DEF", "/src/main.py"])
        assert "def main():" in result

    def test_f_patterns_from_file(self, populated_vfs):
        populated_vfs.write_file("/patterns.txt", "def\nreturn\n")
        result = cmd_grep(populated_vfs, ["-f", "/patterns.txt", "/src/utils.py"])
        assert "def helper():" in result
        assert "return 42" in result

    def test_f_patterns_file_with_path_arg(self, populated_vfs):
        populated_vfs.write_file("/patterns.txt", "def\n")
        result = cmd_grep(populated_vfs, ["-r", "-f", "/patterns.txt", "/src"])
        assert "/src/main.py" in result
        assert "/src/utils.py" in result

    def test_f_multiple_pattern_files(self, populated_vfs):
        populated_vfs.write_file("/p1.txt", "def\n")
        populated_vfs.write_file("/p2.txt", "return\n")
        result = cmd_grep(populated_vfs, ["-f", "/p1.txt", "-f", "/p2.txt", "/src/utils.py"])
        assert "def helper():" in result
        assert "return 42" in result

    def test_f_missing_pattern_file_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="No such file"):
            cmd_grep(populated_vfs, ["-f", "/nonexistent.txt", "/src/main.py"])

    def test_d_recurse_equals_r(self, populated_vfs):
        result_r = cmd_grep(populated_vfs, ["-r", "def", "/src"])
        result_d = cmd_grep(populated_vfs, ["-d", "recurse", "def", "/src"])
        assert result_r == result_d

    def test_d_skip_silently_ignores_dirs(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-d", "skip", "def", "/src"])
        assert result == ""

    def test_d_read_default_raises_on_dir(self, populated_vfs):
        with pytest.raises(CommandError, match="Is a directory"):
            cmd_grep(populated_vfs, ["def", "/src"])

    def test_max_depth_0_top_dir_only(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "--max-depth=0", "def", "/src"])
        assert "/src/main.py" in result
        assert "/src/utils.py" in result
        assert "test_main.py" not in result

    def test_max_depth_1_one_level(self, populated_vfs):
        populated_vfs.write_file("/src/tests/deep/extra.py", "def extra(): pass\n")
        result = cmd_grep(populated_vfs, ["-r", "--max-depth=1", "def", "/src"])
        assert "/src/main.py" in result
        assert "test_main.py" in result   # /src/tests/ is 1 level deep — included
        assert "extra.py" not in result   # /src/tests/deep/ is 2 levels deep — pruned

    def test_max_depth_2_reaches_nested(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "--max-depth=2", "def", "/src"])
        assert "test_main.py" in result

    def test_exclude_dir_skips_subdir(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "--exclude-dir=tests", "def", "/src"])
        assert "main.py" in result
        assert "test_main.py" not in result

    def test_exclude_dir_glob_pattern(self, populated_vfs):
        result = cmd_grep(populated_vfs, ["-r", "--exclude-dir=test*", "def", "/src"])
        assert "main.py" in result
        assert "test_main.py" not in result

    def test_exclude_dir_multiple(self, populated_vfs):
        populated_vfs.write_file("/src/vendor/lib.py", "def vendored(): pass\n")
        result = cmd_grep(populated_vfs, [
            "-r", "--exclude-dir=tests", "--exclude-dir=vendor", "def", "/src",
        ])
        assert "main.py" in result
        assert "test_main.py" not in result
        assert "vendor" not in result

    def test_include_dir_limits_recursion(self, populated_vfs):
        populated_vfs.write_file("/src/vendor/lib.py", "def vendored(): pass\n")
        result = cmd_grep(populated_vfs, ["-r", "--include-dir=tests", "def", "/src"])
        assert "test_main.py" in result    # /src/tests/ is whitelisted — included
        assert "vendor" not in result      # /src/vendor/ is not whitelisted — pruned

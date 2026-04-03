from __future__ import annotations

import pytest
from agent_clifs.commands.file_ops import (
    cmd_append,
    cmd_cp,
    cmd_mkdir,
    cmd_mv,
    cmd_rm,
    cmd_touch,
    cmd_write,
)
from agent_clifs.commands.navigation import cmd_cd, cmd_ls, cmd_pwd, cmd_tree
from agent_clifs.commands.read import cmd_cat, cmd_head, cmd_tail, cmd_view, cmd_wc
from agent_clifs.commands.search import cmd_find, cmd_grep
from agent_clifs.exceptions import CommandError


# ================================================================
# Navigation commands
# ================================================================


class TestPwd:
    def test_returns_cwd(self, populated_vfs):
        assert cmd_pwd(populated_vfs, []) == "/"

    def test_after_chdir(self, populated_vfs):
        populated_vfs.chdir("/docs")
        assert cmd_pwd(populated_vfs, []) == "/docs"


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


class TestLs:
    def test_basic_listing(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["/"])
        assert "docs/" in result
        assert "src/" in result

    def test_long_format(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-l", "/src"])
        assert "tests/" in result
        assert "main.py" in result
        lines = result.strip().splitlines()
        for line in lines:
            assert line[0] in ("d", "f")

    def test_recursive(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-R", "/docs"])
        assert "/docs:" in result
        assert "/docs/api:" in result


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


# ================================================================
# Read commands
# ================================================================


class TestCat:
    def test_single_file(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["/src/utils.py"])
        assert "def helper():" in result

    def test_multiple_files(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["/src/utils.py", "/src/main.py"])
        assert "helper" in result
        assert "main" in result

    def test_numbering(self, populated_vfs):
        result = cmd_cat(populated_vfs, ["-n", "/src/utils.py"])
        assert "1\t" in result
        assert "2\t" in result

    def test_missing_file_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_cat(populated_vfs, ["/nope.txt"])


class TestHead:
    def test_default_lines(self, populated_vfs):
        result = cmd_head(populated_vfs, ["/src/main.py"])
        assert "def main():" in result

    def test_custom_lines(self, populated_vfs):
        result = cmd_head(populated_vfs, ["-n", "2", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) == 2


class TestTail:
    def test_default_lines(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["/src/main.py"])
        assert "main()" in result

    def test_custom_lines(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["-n", "2", "/src/main.py"])
        lines = result.strip().splitlines()
        assert len(lines) == 2


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


# ================================================================
# Search commands
# ================================================================


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


class TestFind:
    def test_find_all(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/"])
        assert "/docs" in result
        assert "/src" in result

    def test_find_name_glob(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-name", "*.py"])
        lines = result.strip().splitlines()
        assert "/src/main.py" in lines
        assert "/src/utils.py" in lines
        for line in lines:
            assert line.endswith(".py")

    def test_find_type_file(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f"])
        lines = result.strip().splitlines()
        for line in lines:
            assert populated_vfs.is_file(line)

    def test_find_type_dir(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "d"])
        lines = result.strip().splitlines()
        for line in lines:
            assert populated_vfs.is_dir(line)

    def test_find_path_pattern(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-path", "*/api/*"])
        lines = result.strip().splitlines()
        assert all("api" in l for l in lines)

    def test_find_maxdepth(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-maxdepth", "1"])
        lines = result.strip().splitlines()
        for line in lines:
            depth = line.count("/")
            assert depth <= 1

    def test_find_combined_filters(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-name", "*.md"])
        lines = result.strip().splitlines()
        for line in lines:
            assert line.endswith(".md")
            assert populated_vfs.is_file(line)

    def test_find_relative_start(self, populated_vfs):
        populated_vfs.chdir("/src")
        result = cmd_find(populated_vfs, [".", "-name", "*.py"])
        lines = result.strip().splitlines()
        assert any(l.startswith(".") for l in lines)

    def test_find_missing_dir_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="No such file"):
            cmd_find(populated_vfs, ["/nope"])


# ================================================================
# File operation commands
# ================================================================


class TestMkdirCmd:
    def test_mkdir(self, vfs):
        cmd_mkdir(vfs, ["/newdir"])
        assert vfs.is_dir("/newdir")

    def test_mkdir_parents(self, vfs):
        cmd_mkdir(vfs, ["-p", "/a/b/c"])
        assert vfs.is_dir("/a/b/c")

    def test_mkdir_existing_raises(self, vfs):
        vfs.mkdir("/dup")
        with pytest.raises(CommandError):
            cmd_mkdir(vfs, ["/dup"])


class TestTouch:
    def test_creates_file(self, vfs):
        cmd_touch(vfs, ["/new.txt"])
        assert vfs.is_file("/new.txt")
        assert vfs.read_file("/new.txt") == ""

    def test_existing_is_noop(self, vfs):
        vfs.write_file("/exist.txt", "data")
        cmd_touch(vfs, ["/exist.txt"])
        assert vfs.read_file("/exist.txt") == "data"


class TestWrite:
    def test_creates_file_with_content(self, vfs):
        cmd_write(vfs, ["/f.txt", "hello", "world"])
        assert vfs.read_file("/f.txt") == "hello world"

    def test_no_args_raises(self, vfs):
        with pytest.raises(CommandError):
            cmd_write(vfs, [])


class TestAppendCmd:
    def test_creates_then_appends(self, vfs):
        cmd_append(vfs, ["/log.txt", "first"])
        cmd_append(vfs, ["/log.txt", " second"])
        assert vfs.read_file("/log.txt") == "first second"

    def test_no_args_raises(self, vfs):
        with pytest.raises(CommandError):
            cmd_append(vfs, [])


class TestRm:
    def test_rm_file(self, populated_vfs):
        cmd_rm(populated_vfs, ["/src/utils.py"])
        assert not populated_vfs.exists("/src/utils.py")

    def test_rm_dir_recursive(self, populated_vfs):
        cmd_rm(populated_vfs, ["-r", "/docs"])
        assert not populated_vfs.exists("/docs")

    def test_rm_dir_without_r_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="Is a directory"):
            cmd_rm(populated_vfs, ["/docs"])

    def test_rm_force_missing_silent(self, populated_vfs):
        cmd_rm(populated_vfs, ["-f", "/nope.txt"])


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


class TestMv:
    def test_mv_file(self, populated_vfs):
        cmd_mv(populated_vfs, ["/src/utils.py", "/src/helpers.py"])
        assert populated_vfs.is_file("/src/helpers.py")
        assert not populated_vfs.exists("/src/utils.py")

    def test_mv_directory(self, populated_vfs):
        cmd_mv(populated_vfs, ["/docs", "/documentation"])
        assert populated_vfs.is_dir("/documentation")
        assert populated_vfs.is_file("/documentation/readme.md")
        assert not populated_vfs.exists("/docs")

    def test_mv_missing_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_mv(populated_vfs, ["/nope", "/dest"])


# ================================================================
# Enhanced navigation commands
# ================================================================


class TestLsEnhanced:
    def test_ls_human_readable(self, populated_vfs):
        populated_vfs.write_file("/bigfile.txt", "x" * 2000)
        result = cmd_ls(populated_vfs, ["-lh", "/"])
        assert "2.0K" in result

    def test_ls_sort_by_size(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-lS", "/src"])
        lines = result.strip().splitlines()
        main_idx = next(i for i, l in enumerate(lines) if "main.py" in l)
        utils_idx = next(i for i, l in enumerate(lines) if "utils.py" in l)
        assert main_idx < utils_idx

    def test_ls_directory_flag(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-d", "/src"])
        assert "src/" in result
        assert "main.py" not in result
        assert "utils.py" not in result

    def test_ls_oneline_accepted(self, populated_vfs):
        result = cmd_ls(populated_vfs, ["-1", "/src"])
        assert "main.py" in result


class TestCdEnhanced:
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


class TestTreeEnhanced:
    def test_tree_d_flag(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-d", "/"])
        assert "directories" in result
        assert "files" not in result
        assert "main.py" not in result

    def test_tree_a_flag_accepted(self, populated_vfs):
        result = cmd_tree(populated_vfs, ["-a", "/"])
        assert "directories" in result


# ================================================================
# Enhanced read commands
# ================================================================


class TestView:
    def test_view_full_file(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py"])
        assert "File: /src/main.py (5 lines)" in result
        assert "1 | def main():" in result
        assert "5 |     main()" in result

    def test_view_line_range(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "2", "4"])
        assert "lines 2-4 of 5" in result
        assert "print('hello')" in result
        assert "def main():" not in result

    def test_view_start_only(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "3"])
        assert "lines 3-5 of 5" in result
        assert "main()" in result

    def test_view_header_shows_range(self, populated_vfs):
        result = cmd_view(populated_vfs, ["/src/main.py", "1", "3"])
        header = result.splitlines()[0]
        assert "lines 1-3 of 5" in header

    def test_view_beyond_end_raises(self, populated_vfs):
        with pytest.raises(CommandError, match="beyond end"):
            cmd_view(populated_vfs, ["/src/main.py", "100"])

    def test_view_missing_file_raises(self, populated_vfs):
        with pytest.raises(CommandError):
            cmd_view(populated_vfs, ["/nonexistent.py"])


class TestCatEnhanced:
    def test_cat_squeeze_blank(self, populated_vfs):
        populated_vfs.write_file("/blank.txt", "a\n\n\n\nb\n")
        result = cmd_cat(populated_vfs, ["-s", "/blank.txt"])
        assert result == "a\n\nb\n"


class TestHeadEnhanced:
    def test_head_bytes(self, populated_vfs):
        result = cmd_head(populated_vfs, ["-c", "5", "/src/utils.py"])
        assert result == "def h"


class TestTailEnhanced:
    def test_tail_bytes(self, populated_vfs):
        content = populated_vfs.read_file("/src/utils.py")
        result = cmd_tail(populated_vfs, ["-c", "5", "/src/utils.py"])
        assert result == content[-5:]

    def test_tail_plus_n(self, populated_vfs):
        result = cmd_tail(populated_vfs, ["-n", "+3", "/src/main.py"])
        assert "if __name__" in result
        assert "main()" in result
        assert "def main():" not in result
        assert "print('hello')" not in result


# ================================================================
# Enhanced search commands
# ================================================================


class TestGrepEnhanced:
    def test_grep_fixed_strings(self, populated_vfs):
        populated_vfs.write_file("/meta.txt", "a.b\na*b\naxb\nnormal\n")
        result = cmd_grep(populated_vfs, ["-F", "a.b", "/meta.txt"])
        lines = result.strip().splitlines()
        assert "a.b" in lines
        assert "axb" not in lines

    def test_grep_multiple_patterns(self, populated_vfs):
        # With -e flags, first positional is consumed by argparse's `pattern`;
        # provide the file twice so the second lands in `paths`.
        result = cmd_grep(populated_vfs, [
            "-e", "def", "-e", "return",
            "/src/utils.py", "/src/utils.py",
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


class TestFindEnhanced:
    def test_find_iname(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-iname", "README*"])
        lines = result.strip().splitlines()
        assert "/docs/readme.md" in lines

    def test_find_mindepth(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-mindepth", "2"])
        lines = result.strip().splitlines()
        assert "/" not in lines
        assert "/docs" not in lines
        assert "/src" not in lines
        assert any("readme.md" in l for l in lines)

    def test_find_not_name(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-not", "-name", "*.md"])
        lines = result.strip().splitlines()
        for line in lines:
            assert not line.endswith(".md")
        assert any(line.endswith(".py") for line in lines)

    def test_find_not_path(self, populated_vfs):
        result = cmd_find(populated_vfs, ["/", "-type", "f", "-not", "-path", "*/docs/*"])
        lines = result.strip().splitlines()
        for line in lines:
            assert "/docs/" not in line
        assert any("src" in line for line in lines)


# ================================================================
# Enhanced file operation commands
# ================================================================


class TestCpEnhanced:
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


class TestMvEnhanced:
    def test_mv_force_accepted(self, populated_vfs):
        cmd_mv(populated_vfs, ["-f", "/src/utils.py", "/src/helpers.py"])
        assert populated_vfs.is_file("/src/helpers.py")

    def test_mv_no_clobber(self, populated_vfs):
        populated_vfs.write_file("/a.txt", "aaa")
        populated_vfs.write_file("/b.txt", "bbb")
        cmd_mv(populated_vfs, ["-n", "/a.txt", "/b.txt"])
        assert populated_vfs.read_file("/b.txt") == "bbb"
        assert populated_vfs.is_file("/a.txt")

    def test_mv_verbose(self, populated_vfs):
        result = cmd_mv(populated_vfs, ["-v", "/src/utils.py", "/src/helpers.py"])
        assert "renamed" in result
        assert "->" in result


class TestRmEnhanced:
    def test_rm_verbose(self, populated_vfs):
        result = cmd_rm(populated_vfs, ["-v", "/src/utils.py"])
        assert "removed" in result
        assert "/src/utils.py" in result


class TestTouchEnhanced:
    def test_touch_no_create(self, populated_vfs):
        cmd_touch(populated_vfs, ["-c", "/nonexistent.txt"])
        assert not populated_vfs.exists("/nonexistent.txt")


class TestMkdirEnhanced:
    def test_mkdir_verbose(self, populated_vfs):
        result = cmd_mkdir(populated_vfs, ["-v", "/newdir"])
        assert "created directory" in result

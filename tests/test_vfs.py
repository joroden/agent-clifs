from __future__ import annotations

import pytest
from agent_clifs.exceptions import (
    FileExistsVFSError,
    FileNotFoundVFSError,
    IsADirectoryVFSError,
    NotADirectoryVFSError,
)
from agent_clifs.vfs import VirtualFileSystem


class TestResolvePath:
    def test_absolute_path(self, vfs):
        assert vfs.resolve_path("/foo/bar") == "/foo/bar"

    def test_relative_path_from_root(self, vfs):
        assert vfs.resolve_path("foo") == "/foo"

    def test_relative_path_with_cwd(self, vfs):
        vfs._cwd = "/home"
        vfs._dirs.add("/home")
        assert vfs.resolve_path("foo") == "/home/foo"

    def test_dot_resolves_to_cwd(self, vfs):
        assert vfs.resolve_path(".") == "/"
        vfs._cwd = "/home"
        vfs._dirs.add("/home")
        assert vfs.resolve_path(".") == "/home"

    def test_dotdot_resolves_to_parent(self, vfs):
        vfs._cwd = "/home/user"
        vfs._dirs.update({"/home", "/home/user"})
        assert vfs.resolve_path("..") == "/home"

    def test_empty_string_resolves_to_cwd(self, vfs):
        assert vfs.resolve_path("") == "/"

    def test_trailing_slash_removed(self, vfs):
        assert vfs.resolve_path("/foo/") == "/foo"

    def test_double_slashes(self, vfs):
        # POSIX normpath preserves leading // (implementation-defined)
        assert vfs.resolve_path("//foo///bar") == "//foo/bar"
        assert vfs.resolve_path("///foo///bar") == "/foo/bar"

    def test_complex_path(self, vfs):
        assert vfs.resolve_path("/a/b/../c/./d") == "/a/c/d"

    def test_dotdot_from_root(self, vfs):
        assert vfs.resolve_path("/..") == "/"

    def test_root_stays_root(self, vfs):
        assert vfs.resolve_path("/") == "/"


class TestFileOperations:
    def test_write_read_roundtrip(self, vfs):
        vfs.write_file("/hello.txt", "world")
        assert vfs.read_file("/hello.txt") == "world"

    def test_write_auto_creates_parents(self, vfs):
        vfs.write_file("/a/b/c/file.txt", "deep")
        assert vfs.is_dir("/a")
        assert vfs.is_dir("/a/b")
        assert vfs.is_dir("/a/b/c")
        assert vfs.read_file("/a/b/c/file.txt") == "deep"

    def test_write_to_existing_dir_raises(self, vfs):
        vfs.mkdir("/mydir")
        with pytest.raises(IsADirectoryVFSError):
            vfs.write_file("/mydir", "oops")

    def test_read_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.read_file("/nope.txt")

    def test_read_dir_raises(self, vfs):
        vfs.mkdir("/adir")
        with pytest.raises(IsADirectoryVFSError):
            vfs.read_file("/adir")

    def test_append_creates_new(self, vfs):
        vfs.append_file("/new.txt", "first")
        assert vfs.read_file("/new.txt") == "first"

    def test_append_to_existing(self, vfs):
        vfs.write_file("/log.txt", "line1\n")
        vfs.append_file("/log.txt", "line2\n")
        assert vfs.read_file("/log.txt") == "line1\nline2\n"

    def test_remove_file(self, vfs):
        vfs.write_file("/tmp.txt", "bye")
        vfs.remove_file("/tmp.txt")
        assert not vfs.exists("/tmp.txt")

    def test_remove_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.remove_file("/ghost.txt")

    def test_remove_dir_raises(self, vfs):
        vfs.mkdir("/stuff")
        with pytest.raises(IsADirectoryVFSError):
            vfs.remove_file("/stuff")


class TestDirectoryOperations:
    def test_mkdir_creates_dir(self, vfs):
        vfs.mkdir("/newdir")
        assert vfs.is_dir("/newdir")

    def test_mkdir_without_parents_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.mkdir("/a/b/c")

    def test_mkdir_parents(self, vfs):
        vfs.mkdir("/a/b/c", parents=True)
        assert vfs.is_dir("/a")
        assert vfs.is_dir("/a/b")
        assert vfs.is_dir("/a/b/c")

    def test_mkdir_existing_raises(self, vfs):
        vfs.mkdir("/dup")
        with pytest.raises(FileExistsVFSError):
            vfs.mkdir("/dup")

    def test_mkdir_parents_existing_silent(self, vfs):
        vfs.mkdir("/ok")
        vfs.mkdir("/ok", parents=True)

    def test_rmdir_empty(self, vfs):
        vfs.mkdir("/empty")
        vfs.rmdir("/empty")
        assert not vfs.exists("/empty")

    def test_rmdir_nonempty_raises(self, vfs):
        vfs.mkdir("/parent")
        vfs.write_file("/parent/f.txt", "x")
        with pytest.raises(FileExistsVFSError):
            vfs.rmdir("/parent")

    def test_rmdir_recursive(self, vfs):
        vfs.write_file("/tree/a/b.txt", "deep")
        vfs.rmdir("/tree", recursive=True)
        assert not vfs.exists("/tree")
        assert not vfs.exists("/tree/a")

    def test_list_dir_sorted(self, populated_vfs):
        children = populated_vfs.list_dir("/")
        assert children == ["docs", "src"]

    def test_list_dir_on_file_raises(self, vfs):
        vfs.write_file("/f.txt", "hi")
        with pytest.raises(NotADirectoryVFSError):
            vfs.list_dir("/f.txt")

    def test_list_dir_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.list_dir("/nope")


class TestCopyMove:
    def test_copy_file_basic(self, vfs):
        vfs.write_file("/orig.txt", "data")
        vfs.copy_file("/orig.txt", "/copy.txt")
        assert vfs.read_file("/copy.txt") == "data"
        assert vfs.read_file("/orig.txt") == "data"

    def test_copy_file_to_directory(self, vfs):
        vfs.write_file("/src.txt", "content")
        vfs.mkdir("/dest")
        vfs.copy_file("/src.txt", "/dest")
        assert vfs.read_file("/dest/src.txt") == "content"

    def test_move_file(self, vfs):
        vfs.write_file("/old.txt", "move me")
        vfs.move("/old.txt", "/new.txt")
        assert vfs.read_file("/new.txt") == "move me"
        assert not vfs.exists("/old.txt")

    def test_move_directory(self, vfs):
        vfs.write_file("/proj/a.txt", "aa")
        vfs.write_file("/proj/sub/b.txt", "bb")
        vfs.mkdir("/dest")
        vfs.move("/proj", "/dest")
        assert vfs.read_file("/dest/proj/a.txt") == "aa"
        assert vfs.read_file("/dest/proj/sub/b.txt") == "bb"
        assert not vfs.exists("/proj")

    def test_copy_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.copy_file("/nope.txt", "/dst.txt")

    def test_move_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.move("/nope.txt", "/dst.txt")


class TestQueries:
    def test_exists_file(self, vfs):
        vfs.write_file("/x.txt", "")
        assert vfs.exists("/x.txt")

    def test_exists_dir(self, vfs):
        vfs.mkdir("/d")
        assert vfs.exists("/d")

    def test_exists_missing(self, vfs):
        assert not vfs.exists("/nope")

    def test_is_file(self, vfs):
        vfs.write_file("/f.txt", "")
        assert vfs.is_file("/f.txt")
        assert not vfs.is_file("/")

    def test_is_dir(self, vfs):
        assert vfs.is_dir("/")
        vfs.write_file("/f.txt", "")
        assert not vfs.is_dir("/f.txt")

    def test_stat_file(self, vfs):
        vfs.write_file("/f.txt", "hello")
        info = vfs.stat("/f.txt")
        assert info == {"type": "file", "size": 5}

    def test_stat_dir(self, populated_vfs):
        info = populated_vfs.stat("/")
        assert info["type"] == "directory"
        assert info["children"] == 2

    def test_stat_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.stat("/nope")


class TestWalk:
    def test_walk_structure(self, populated_vfs):
        results = list(populated_vfs.walk("/"))
        dirpaths = [r[0] for r in results]
        assert "/" in dirpaths
        assert "/docs" in dirpaths
        assert "/src" in dirpaths

    def test_walk_sorted(self, populated_vfs):
        results = list(populated_vfs.walk("/"))
        root = results[0]
        assert root[0] == "/"
        assert root[1] == ["docs", "src"]

    def test_walk_empty_dir(self, vfs):
        vfs.mkdir("/empty")
        results = list(vfs.walk("/empty"))
        assert results == [("/empty", [], [])]

    def test_walk_files_and_dirs(self, populated_vfs):
        results = list(populated_vfs.walk("/src"))
        assert results[0] == ("/src", ["tests"], ["main.py", "utils.py"])

    def test_walk_nonexistent(self, vfs):
        results = list(vfs.walk("/nope"))
        assert results == []


class TestBulkOperations:
    def test_load_and_export_roundtrip(self, vfs):
        data = {"/a.txt": "aaa", "/b/c.txt": "bbb"}
        vfs.load_from_dict(data)
        exported = vfs.to_dict()
        assert exported == data

    def test_load_creates_parents(self, vfs):
        vfs.load_from_dict({"/deep/nested/file.txt": "x"})
        assert vfs.is_dir("/deep")
        assert vfs.is_dir("/deep/nested")


class TestNavigation:
    def test_cwd_default(self, vfs):
        assert vfs.cwd == "/"

    def test_chdir_and_cwd(self, populated_vfs):
        populated_vfs.chdir("/docs")
        assert populated_vfs.cwd == "/docs"

    def test_chdir_missing_raises(self, vfs):
        with pytest.raises(FileNotFoundVFSError):
            vfs.chdir("/nope")

    def test_chdir_to_file_raises(self, vfs):
        vfs.write_file("/f.txt", "")
        with pytest.raises(NotADirectoryVFSError):
            vfs.chdir("/f.txt")

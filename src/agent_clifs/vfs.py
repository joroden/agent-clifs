"""Core virtual filesystem implementation."""

from __future__ import annotations

from collections.abc import Iterator
from posixpath import normpath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_clifs.bm25 import BM25Index

from agent_clifs.exceptions import (
    FileExistsVFSError,
    FileNotFoundVFSError,
    IsADirectoryVFSError,
    NotADirectoryVFSError,
)


class VirtualFileSystem:
    """A dictionary-backed virtual filesystem for AI agents.

    Files are stored as ``{absolute_path: content}`` strings.
    Directories are tracked explicitly in a set.
    All paths use POSIX-style forward slashes.
    """

    def __init__(self) -> None:
        self._files: dict[str, str] = {}
        self._dirs: set[str] = {"/"}
        self._cwd: str = "/"
        self._bm25_index: BM25Index | None = None
        self._bm25_top_n: int = 10

    # ------------------------------------------------------------------
    # Path handling
    # ------------------------------------------------------------------

    def resolve_path(self, path: str) -> str:
        """Resolve *path* relative to cwd and normalize it.

        Returns an absolute POSIX path with no trailing slash (except ``"/"``).
        """
        if not path:
            return self._cwd

        if not path.startswith("/"):
            path = self._cwd.rstrip("/") + "/" + path

        resolved = normpath(path)
        if not resolved.startswith("/"):
            resolved = "/"
        return resolved

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def exists(self, path: str) -> bool:
        """Return ``True`` if *path* is an existing file or directory."""
        p = self.resolve_path(path)
        return p in self._files or p in self._dirs

    def is_file(self, path: str) -> bool:
        """Return ``True`` if *path* is an existing file."""
        return self.resolve_path(path) in self._files

    def is_dir(self, path: str) -> bool:
        """Return ``True`` if *path* is an existing directory."""
        return self.resolve_path(path) in self._dirs

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def read_file(self, path: str) -> str:
        """Return the contents of the file at *path*."""
        p = self.resolve_path(path)
        if p in self._dirs:
            raise IsADirectoryVFSError(p)
        if p not in self._files:
            raise FileNotFoundVFSError(p)
        return self._files[p]

    def write_file(self, path: str, content: str) -> None:
        """Write *content* to the file at *path*, creating parent dirs."""
        p = self.resolve_path(path)
        if p in self._dirs:
            raise IsADirectoryVFSError(p)
        self._ensure_parents(p)
        self._files[p] = content

    def append_file(self, path: str, content: str) -> None:
        """Append *content* to the file at *path*, creating it if needed."""
        p = self.resolve_path(path)
        if p in self._dirs:
            raise IsADirectoryVFSError(p)
        self._ensure_parents(p)
        self._files[p] = self._files.get(p, "") + content

    def remove_file(self, path: str) -> None:
        """Remove the file at *path*."""
        p = self.resolve_path(path)
        if p in self._dirs:
            raise IsADirectoryVFSError(p)
        if p not in self._files:
            raise FileNotFoundVFSError(p)
        del self._files[p]

    def copy_file(self, src: str, dst: str) -> None:
        """Copy file from *src* to *dst*.

        If *dst* is a directory the file is copied into it keeping the
        original filename.
        """
        sp = self.resolve_path(src)
        dp = self.resolve_path(dst)
        if sp not in self._files:
            if sp in self._dirs:
                raise IsADirectoryVFSError(sp)
            raise FileNotFoundVFSError(sp)
        if dp in self._dirs:
            name = sp.rsplit("/", 1)[-1]
            dp = dp.rstrip("/") + "/" + name
        self._ensure_parents(dp)
        self._files[dp] = self._files[sp]

    def move(self, src: str, dst: str) -> None:
        """Move a file or directory from *src* to *dst*.

        If *dst* is an existing directory the source is moved inside it.
        """
        sp = self.resolve_path(src)
        dp = self.resolve_path(dst)

        if sp not in self._files and sp not in self._dirs:
            raise FileNotFoundVFSError(sp)

        if dp in self._dirs:
            name = sp.rsplit("/", 1)[-1]
            dp = dp.rstrip("/") + "/" + name

        if sp in self._files:
            self._ensure_parents(dp)
            self._files[dp] = self._files.pop(sp)
            return

        # Moving a directory: relocate all nested dirs and files.
        prefix = sp if sp == "/" else sp + "/"
        new_dirs: list[str] = []
        old_dirs: list[str] = []
        for d in list(self._dirs):
            if d == sp or d.startswith(prefix):
                suffix = d[len(sp) :]
                new_dirs.append(dp + suffix)
                old_dirs.append(d)

        new_files: dict[str, str] = {}
        old_file_keys: list[str] = []
        for f in list(self._files):
            if f.startswith(prefix):
                suffix = f[len(sp) :]
                new_files[dp + suffix] = self._files[f]
                old_file_keys.append(f)

        for d in old_dirs:
            self._dirs.discard(d)
        for f in old_file_keys:
            del self._files[f]

        self._ensure_parents(dp)
        self._dirs.update(new_dirs)
        self._files.update(new_files)

    # ------------------------------------------------------------------
    # Directory operations
    # ------------------------------------------------------------------

    def mkdir(self, path: str, parents: bool = False) -> None:
        """Create a directory at *path*.

        With *parents=True* intermediate directories are created silently.
        """
        p = self.resolve_path(path)
        if p in self._files:
            raise FileExistsVFSError(p)

        if parents:
            self._create_parents_and_self(p)
            return

        if p in self._dirs:
            raise FileExistsVFSError(p)
        parent = self._parent(p)
        if parent not in self._dirs:
            raise FileNotFoundVFSError(parent)
        self._dirs.add(p)

    def rmdir(self, path: str, recursive: bool = False) -> None:
        """Remove the directory at *path*.

        With *recursive=True* all contents are removed as well.
        """
        p = self.resolve_path(path)
        if p in self._files:
            raise NotADirectoryVFSError(p)
        if p not in self._dirs:
            raise FileNotFoundVFSError(p)
        if p == "/":
            if not recursive:
                if self._files or len(self._dirs) > 1:
                    raise FileExistsVFSError("directory not empty: /")
                return
            self._files.clear()
            self._dirs.clear()
            self._dirs.add("/")
            return

        prefix = p + "/"
        children_dirs = [d for d in self._dirs if d.startswith(prefix)]
        children_files = [f for f in self._files if f.startswith(prefix)]

        if not recursive and (children_dirs or children_files):
            raise FileExistsVFSError(f"directory not empty: {p}")

        for d in children_dirs:
            self._dirs.discard(d)
        for f in children_files:
            del self._files[f]
        self._dirs.discard(p)

    def list_dir(self, path: str) -> list[str]:
        """Return the names of immediate children of *path*."""
        p = self.resolve_path(path)
        if p in self._files:
            raise NotADirectoryVFSError(p)
        if p not in self._dirs:
            raise FileNotFoundVFSError(p)

        prefix = p if p == "/" else p + "/"
        names: set[str] = set()

        for f in self._files:
            if f.startswith(prefix):
                rest = f[len(prefix) :]
                if rest:
                    names.add(rest.split("/", 1)[0])

        for d in self._dirs:
            if d.startswith(prefix) and d != p:
                rest = d[len(prefix) :]
                if rest:
                    names.add(rest.split("/", 1)[0])

        return sorted(names)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @property
    def cwd(self) -> str:
        """Return the current working directory."""
        return self._cwd

    def chdir(self, path: str) -> None:
        """Change the current working directory to *path*."""
        p = self.resolve_path(path)
        if p in self._files:
            raise NotADirectoryVFSError(p)
        if p not in self._dirs:
            raise FileNotFoundVFSError(p)
        self._cwd = p

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def walk(self, top: str = "/") -> Iterator[tuple[str, list[str], list[str]]]:
        """Walk the directory tree starting at *top*.

        Yields ``(dirpath, dirnames, filenames)`` like :func:`os.walk`.
        Output is sorted for determinism.
        """
        t = self.resolve_path(top)
        if t not in self._dirs:
            return

        prefix = t if t == "/" else t + "/"
        child_dirs: list[str] = []
        child_files: list[str] = []

        for d in sorted(self._dirs):
            if d.startswith(prefix) and d != t:
                rest = d[len(prefix) :]
                if "/" not in rest:
                    child_dirs.append(rest)

        for f in sorted(self._files):
            if f.startswith(prefix):
                rest = f[len(prefix) :]
                if "/" not in rest and rest:
                    child_files.append(rest)

        yield t, child_dirs, child_files

        for d in child_dirs:
            child_path = prefix + d if t == "/" else t + "/" + d
            yield from self.walk(child_path)

    # ------------------------------------------------------------------
    # Bulk loading helpers
    # ------------------------------------------------------------------

    def load_from_dict(self, files: dict[str, str]) -> None:
        """Load multiple files from a ``{path: content}`` dictionary."""
        for path, content in files.items():
            self.write_file(path, content)

    def to_dict(self) -> dict[str, str]:
        """Export all files as a ``{path: content}`` dictionary."""
        return dict(self._files)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def stat(self, path: str) -> dict:
        """Return metadata for *path*.

        Files: ``{"type": "file", "size": <int>}``
        Dirs:  ``{"type": "directory", "children": <int>}``
        """
        p = self.resolve_path(path)
        if p in self._files:
            return {"type": "file", "size": len(self._files[p])}
        if p in self._dirs:
            return {"type": "directory", "children": len(self.list_dir(p))}
        raise FileNotFoundVFSError(p)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parent(p: str) -> str:
        if p == "/":
            return "/"
        return p.rsplit("/", 1)[0] or "/"

    def _ensure_parents(self, path: str) -> None:
        parts = path.strip("/").split("/")[:-1]
        current = ""
        for part in parts:
            current += "/" + part
            self._dirs.add(current)

    def _create_parents_and_self(self, path: str) -> None:
        parts = path.strip("/").split("/")
        current = ""
        for part in parts:
            current += "/" + part
            self._dirs.add(current)

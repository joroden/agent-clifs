"""Navigation commands: pwd, cd, ls, tree."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from agent_clifs.exceptions import CommandError, VFSError

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem

_previous_dirs: dict[int, str] = {}


# ------------------------------------------------------------------
# Argparse helper
# ------------------------------------------------------------------

class _CommandArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises CommandError instead of calling sys.exit."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise CommandError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            raise CommandError(message.strip())
        raise CommandError("")


def _make_parser(prog: str, description: str) -> _CommandArgumentParser:
    return _CommandArgumentParser(prog=prog, description=description, add_help=False)


# ------------------------------------------------------------------
# pwd
# ------------------------------------------------------------------

def cmd_pwd(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Print the current working directory."""
    parser = _make_parser("pwd", "Print the current working directory")
    parser.parse_args(args)
    return vfs.cwd


# ------------------------------------------------------------------
# cd
# ------------------------------------------------------------------

def cmd_cd(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Change the current working directory."""
    parser = _make_parser("cd", "Change the current working directory")
    parser.add_argument("directory", nargs="?", default="/")
    parsed = parser.parse_args(args)

    target = parsed.directory
    if target == "~":
        target = "/"
    elif target == "-":
        vfs_id = id(vfs)
        if vfs_id not in _previous_dirs:
            raise CommandError("cd: no previous directory")
        target = _previous_dirs[vfs_id]

    old_cwd = vfs.cwd
    try:
        vfs.chdir(target)
    except VFSError as exc:
        raise CommandError(f"cd: {exc}") from exc
    _previous_dirs[id(vfs)] = old_cwd
    return ""


# ------------------------------------------------------------------
# ls
# ------------------------------------------------------------------

def _human_readable_size(size_bytes: int) -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(size_bytes) < 1024:
            if unit == "":
                return str(size_bytes)
            return f"{size_bytes:.1f}{unit}"
        size_bytes = size_bytes / 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f}P"


def cmd_ls(vfs: VirtualFileSystem, args: list[str]) -> str:
    """List directory contents."""
    parser = _make_parser("ls", "List directory contents")
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("-l", "--long", action="store_true")
    parser.add_argument("-a", "--all", action="store_true")
    parser.add_argument("-R", "--recursive", action="store_true")
    parser.add_argument("-h", "--human-readable", action="store_true")
    parser.add_argument("-S", "--sort-size", action="store_true")
    parser.add_argument("-1", "--oneline", action="store_true")
    parser.add_argument("-d", "--directory", action="store_true")
    parser.add_argument("-r", "--reverse", action="store_true")
    parser.add_argument("-F", "--classify", action="store_true")
    parsed = parser.parse_args(args)

    multiple = len(parsed.paths) > 1
    sections: list[str] = []

    for path in parsed.paths:
        try:
            resolved = vfs.resolve_path(path)
            if parsed.directory:
                sections.append(_ls_directory_entry(vfs, path, parsed.long, parsed.human_readable))
            elif vfs.is_file(resolved):
                name = resolved.rsplit("/", 1)[-1]
                sections.append(_format_entry(vfs, resolved, name, parsed.long, parsed.human_readable))
            elif parsed.recursive:
                sections.append(_ls_recursive(
                    vfs, path, parsed.long,
                    show_header=multiple,
                    human=parsed.human_readable,
                    sort_size=parsed.sort_size,
                    show_all=parsed.all,
                    reverse=parsed.reverse,
                ))
            else:
                sections.append(_ls_single(
                    vfs, path, parsed.long,
                    show_header=multiple,
                    human=parsed.human_readable,
                    sort_size=parsed.sort_size,
                    show_all=parsed.all,
                    reverse=parsed.reverse,
                ))
        except VFSError as exc:
            raise CommandError(f"ls: {exc}") from exc

    return "\n\n".join(sections)


def _ls_directory_entry(
    vfs: VirtualFileSystem,
    path: str,
    long: bool,
    human: bool,
) -> str:
    resolved = vfs.resolve_path(path)
    name = resolved.rsplit("/", 1)[-1] or "/"
    if vfs.is_dir(resolved):
        display = name + "/" if name != "/" else "/"
    else:
        display = name
    return _format_entry(vfs, resolved, display, long, human)


def _sort_entries_by_size(vfs: VirtualFileSystem, dirpath: str, names: list[str]) -> list[str]:
    def size_key(name: str) -> int:
        child_path = dirpath.rstrip("/") + "/" + name
        info = vfs.stat(child_path)
        if info["type"] == "file":
            return info["size"]
        return info["children"]
    return sorted(names, key=size_key, reverse=True)


def _ls_single(
    vfs: VirtualFileSystem,
    path: str,
    long: bool,
    *,
    show_header: bool,
    human: bool = False,
    sort_size: bool = False,
    show_all: bool = True,
    reverse: bool = False,
) -> str:
    resolved = vfs.resolve_path(path)
    entries = vfs.list_dir(resolved)
    if not show_all:
        entries = [e for e in entries if not e.startswith(".")]
    if sort_size:
        entries = _sort_entries_by_size(vfs, resolved, entries)
    if reverse:
        entries = list(reversed(entries))
    lines: list[str] = []

    if show_header:
        lines.append(f"{resolved}:")

    for name in entries:
        child_path = resolved.rstrip("/") + "/" + name
        lines.append(_format_entry(vfs, child_path, name, long, human))

    return "\n".join(lines)


def _ls_recursive(
    vfs: VirtualFileSystem,
    path: str,
    long: bool,
    *,
    show_header: bool,
    human: bool = False,
    sort_size: bool = False,
    show_all: bool = True,
    reverse: bool = False,
) -> str:
    resolved = vfs.resolve_path(path)
    sections: list[str] = []

    for dirpath, dirnames, filenames in vfs.walk(resolved):
        lines: list[str] = [f"{dirpath}:"]
        names = sorted(dirnames + filenames)
        if not show_all:
            names = [n for n in names if not n.startswith(".")]
        if sort_size:
            names = _sort_entries_by_size(vfs, dirpath, names)
        if reverse:
            names = list(reversed(names))
        for name in names:
            child_path = dirpath.rstrip("/") + "/" + name
            lines.append(_format_entry(vfs, child_path, name, long, human))
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _format_entry(
    vfs: VirtualFileSystem,
    full_path: str,
    name: str,
    long: bool,
    human: bool = False,
) -> str:
    if vfs.is_dir(full_path):
        if long:
            info = vfs.stat(full_path)
            return f"d  {info['children']}  {name}/" if not name.endswith("/") else f"d  {info['children']}  {name}"
        return f"{name}/" if not name.endswith("/") else name
    if long:
        info = vfs.stat(full_path)
        size = _human_readable_size(info["size"]) if human else str(info["size"])
        return f"f  {size}  {name}"
    return name


# ------------------------------------------------------------------
# tree
# ------------------------------------------------------------------

def cmd_tree(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Display a tree visualization of the directory structure."""
    parser = _make_parser("tree", "Display directory tree")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("-L", "--level", type=int, default=None)
    parser.add_argument("-d", "--dirs-only", action="store_true")
    parser.add_argument("-a", "--all", action="store_true")
    parsed = parser.parse_args(args)

    try:
        resolved = vfs.resolve_path(parsed.path)
        if not vfs.is_dir(resolved):
            raise CommandError(f"tree: {resolved}: not a directory")

        lines: list[str] = [resolved]
        dir_count = 0
        file_count = 0

        d, f = _tree_walk(vfs, resolved, "", parsed.level, 0, parsed.dirs_only, lines)
        dir_count += d
        file_count += f

        if parsed.dirs_only:
            lines.append(f"\n{dir_count} directories")
        else:
            lines.append(f"\n{dir_count} directories, {file_count} files")

        return "\n".join(lines)
    except VFSError as exc:
        raise CommandError(f"tree: {exc}") from exc


def _tree_walk(
    vfs: VirtualFileSystem,
    dirpath: str,
    prefix: str,
    max_level: int | None,
    current_level: int,
    dirs_only: bool,
    lines: list[str],
) -> tuple[int, int]:
    if max_level is not None and current_level >= max_level:
        return 0, 0

    entries: list[str] = vfs.list_dir(dirpath)
    dirs = [e for e in entries if vfs.is_dir(dirpath.rstrip("/") + "/" + e)]
    files = [e for e in entries if vfs.is_file(dirpath.rstrip("/") + "/" + e)]

    if dirs_only:
        visible = dirs
    else:
        visible = sorted(dirs + files)

    dir_count = 0
    file_count = 0

    for i, name in enumerate(visible):
        is_last = i == len(visible) - 1
        connector = "└── " if is_last else "├── "
        child_path = dirpath.rstrip("/") + "/" + name

        if name in dirs:
            lines.append(f"{prefix}{connector}{name}/")
            dir_count += 1
            child_prefix = prefix + ("    " if is_last else "│   ")
            d, f = _tree_walk(
                vfs, child_path, child_prefix, max_level, current_level + 1, dirs_only, lines
            )
            dir_count += d
            file_count += f
        else:
            lines.append(f"{prefix}{connector}{name}")
            file_count += 1

    return dir_count, file_count

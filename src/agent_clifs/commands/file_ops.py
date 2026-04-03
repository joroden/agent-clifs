"""File operation commands for the virtual filesystem."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from agent_clifs.exceptions import (
    CommandError,
    FileExistsVFSError,
    FileNotFoundVFSError,
    IsADirectoryVFSError,
    NotADirectoryVFSError,
)

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem


# ------------------------------------------------------------------
# Argument parsing helper
# ------------------------------------------------------------------


class _NoExitParser(argparse.ArgumentParser):
    """ArgumentParser subclass that raises CommandError instead of exiting."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise CommandError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            raise CommandError(message.strip())
        raise CommandError(f"{self.prog}: unexpected exit")


def _make_parser(prog: str, description: str) -> _NoExitParser:
    return _NoExitParser(prog=prog, description=description, add_help=False)


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------


def cmd_mkdir(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Create directories."""
    parser = _make_parser("mkdir", "Create directories")
    parser.add_argument("-p", "--parents", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("paths", nargs="+", metavar="DIR")
    ns = parser.parse_args(args)

    lines: list[str] = []
    for path in ns.paths:
        try:
            if ns.verbose and ns.parents:
                resolved = vfs.resolve_path(path)
                parts = resolved.strip("/").split("/")
                current = ""
                for part in parts:
                    current += "/" + part
                    if not vfs.is_dir(current):
                        lines.append(f"mkdir: created directory '{current}'")
            vfs.mkdir(path, parents=ns.parents)
            if ns.verbose and not ns.parents:
                lines.append(
                    f"mkdir: created directory '{vfs.resolve_path(path)}'"
                )
        except (FileExistsVFSError, FileNotFoundVFSError) as exc:
            raise CommandError(f"mkdir: {exc}") from exc
    return "\n".join(lines)


def cmd_touch(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Create files if they don't exist."""
    parser = _make_parser("touch", "Create files")
    parser.add_argument("-c", "--no-create", action="store_true")
    parser.add_argument("paths", nargs="+", metavar="FILE")
    ns = parser.parse_args(args)

    for path in ns.paths:
        if not vfs.is_file(path):
            if ns.no_create:
                continue
            try:
                vfs.write_file(path, "")
            except (IsADirectoryVFSError, FileNotFoundVFSError) as exc:
                raise CommandError(f"touch: {exc}") from exc
    return ""


def cmd_write(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Write content to a file."""
    if not args:
        raise CommandError("write: missing file operand")
    path = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else ""
    try:
        vfs.write_file(path, content)
    except (IsADirectoryVFSError, FileNotFoundVFSError) as exc:
        raise CommandError(f"write: {exc}") from exc
    return ""


def cmd_append(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Append content to a file."""
    if not args:
        raise CommandError("append: missing file operand")
    path = args[0]
    content = " ".join(args[1:]) if len(args) > 1 else ""
    try:
        vfs.append_file(path, content)
    except (IsADirectoryVFSError, FileNotFoundVFSError) as exc:
        raise CommandError(f"append: {exc}") from exc
    return ""


def cmd_rm(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Remove files and directories."""
    parser = _make_parser("rm", "Remove files and directories")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("paths", nargs="+", metavar="PATH")
    ns = parser.parse_args(args)

    lines: list[str] = []
    for path in ns.paths:
        try:
            if vfs.is_dir(path):
                if not ns.recursive:
                    raise CommandError(f"rm: cannot remove '{path}': Is a directory")
                if ns.verbose:
                    resolved = vfs.resolve_path(path)
                    all_dirs: list[str] = []
                    for dirpath, _dirnames, filenames in vfs.walk(resolved):
                        for fname in filenames:
                            fpath = dirpath.rstrip("/") + "/" + fname
                            lines.append(f"removed '{fpath}'")
                        all_dirs.append(dirpath)
                    for d in reversed(all_dirs):
                        lines.append(f"removed '{d}'")
                vfs.rmdir(path, recursive=True)
            elif vfs.is_file(path):
                if ns.verbose:
                    lines.append(f"removed '{vfs.resolve_path(path)}'")
                vfs.remove_file(path)
            else:
                if not ns.force:
                    raise CommandError(
                        f"rm: cannot remove '{path}': No such file or directory"
                    )
        except CommandError:
            raise
        except (
            FileNotFoundVFSError,
            IsADirectoryVFSError,
            NotADirectoryVFSError,
        ) as exc:
            if not ns.force:
                raise CommandError(f"rm: {exc}") from exc
    return "\n".join(lines)


def cmd_cp(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Copy files and directories."""
    parser = _make_parser("cp", "Copy files and directories")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("-a", "--archive", action="store_true")
    parser.add_argument("-n", "--no-clobber", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("source", metavar="SRC")
    parser.add_argument("destination", metavar="DST")
    ns = parser.parse_args(args)

    if ns.archive:
        ns.recursive = True

    src, dst = ns.source, ns.destination
    lines: list[str] = []

    try:
        if vfs.is_dir(src):
            if not ns.recursive:
                raise CommandError(f"cp: -r not specified; omitting directory '{src}'")
            lines = _copy_dir_recursive(
                vfs, src, dst, no_clobber=ns.no_clobber, verbose=ns.verbose,
            )
        else:
            if ns.no_clobber:
                dst_r = vfs.resolve_path(dst)
                if vfs.is_dir(dst_r):
                    name = vfs.resolve_path(src).rsplit("/", 1)[-1]
                    actual = dst_r.rstrip("/") + "/" + name
                else:
                    actual = dst_r
                if vfs.is_file(actual):
                    return ""
            vfs.copy_file(src, dst)
            if ns.verbose:
                src_r = vfs.resolve_path(src)
                dst_r = vfs.resolve_path(dst)
                if vfs.is_dir(dst_r):
                    name = src_r.rsplit("/", 1)[-1]
                    dst_r = dst_r.rstrip("/") + "/" + name
                lines.append(f"'{src_r}' -> '{dst_r}'")
    except CommandError:
        raise
    except (
        FileNotFoundVFSError,
        IsADirectoryVFSError,
        FileExistsVFSError,
    ) as exc:
        raise CommandError(f"cp: {exc}") from exc
    return "\n".join(lines)


def _copy_dir_recursive(
    vfs: VirtualFileSystem,
    src: str,
    dst: str,
    *,
    no_clobber: bool = False,
    verbose: bool = False,
) -> list[str]:
    lines: list[str] = []
    src_resolved = vfs.resolve_path(src)
    dst_resolved = vfs.resolve_path(dst)

    if vfs.is_dir(dst):
        name = src_resolved.rsplit("/", 1)[-1]
        dst_resolved = dst_resolved.rstrip("/") + "/" + name

    for dirpath, dirnames, filenames in vfs.walk(src_resolved):
        rel = dirpath[len(src_resolved):]
        target_dir = dst_resolved + rel
        vfs.mkdir(target_dir, parents=True)
        for fname in filenames:
            src_file = dirpath.rstrip("/") + "/" + fname
            dst_file = target_dir.rstrip("/") + "/" + fname
            if no_clobber and vfs.is_file(dst_file):
                continue
            vfs.copy_file(src_file, dst_file)
            if verbose:
                lines.append(f"'{src_file}' -> '{dst_file}'")
    return lines


def cmd_mv(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Move or rename files and directories."""
    parser = _make_parser("mv", "Move files and directories")
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("-n", "--no-clobber", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("source", metavar="SRC")
    parser.add_argument("destination", metavar="DST")
    ns = parser.parse_args(args)

    src, dst = ns.source, ns.destination

    if ns.no_clobber:
        dst_r = vfs.resolve_path(dst)
        if vfs.is_dir(dst_r):
            src_r = vfs.resolve_path(src)
            name = src_r.rsplit("/", 1)[-1]
            actual = dst_r.rstrip("/") + "/" + name
        else:
            actual = dst_r
        if vfs.exists(actual):
            return ""

    try:
        vfs.move(src, dst)
    except (FileNotFoundVFSError, FileExistsVFSError) as exc:
        raise CommandError(f"mv: {exc}") from exc

    if ns.verbose:
        return f"renamed '{src}' -> '{dst}'"
    return ""

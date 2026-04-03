"""Search commands for the virtual filesystem."""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from typing import TYPE_CHECKING

from agent_clifs.exceptions import CommandError, FileNotFoundVFSError, IsADirectoryVFSError

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem


# ------------------------------------------------------------------
# Argument parsing helper
# ------------------------------------------------------------------

class _VFSArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises CommandError instead of calling sys.exit."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise CommandError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            raise CommandError(message.strip())
        raise CommandError("")


def _make_parser(prog: str, description: str) -> _VFSArgumentParser:
    return _VFSArgumentParser(prog=prog, description=description, add_help=False)


# ------------------------------------------------------------------
# ReDoS protection
# ------------------------------------------------------------------

# Detects groups containing a quantifier followed by an outer quantifier,
# e.g. (a+)+, (a|a?)+, (?:x+)*, (x{2,})+.
# Static rejection of known-dangerous structures is the only reliable defence.
_NESTED_QUANTIFIER_RE = re.compile(r"\([^()]*[+*?{][^()]*\)[+*?{]")


def _check_for_redos(pattern: str) -> None:
    """Raise CommandError if *pattern* contains nested quantifiers.

    Nested quantifiers such as ``(a+)+`` or ``(a|a?)+`` cause catastrophic
    backtracking in Python's regex engine.  Use ``-F`` for literal matching
    to bypass this check.
    """
    if _NESTED_QUANTIFIER_RE.search(pattern):
        raise CommandError(
            "grep: pattern contains nested quantifiers that may cause "
            "catastrophic backtracking. Use -F for literal string matching."
        )


def _match_lines(regex: re.Pattern[str], lines: list[str], invert: bool) -> set[int]:
    return {i for i, line in enumerate(lines) if bool(regex.search(line)) != invert}


# ------------------------------------------------------------------
# grep
# ------------------------------------------------------------------

def _collect_files(vfs: VirtualFileSystem, paths: list[str], recursive: bool) -> list[str]:
    """Resolve *paths* into a flat sorted list of absolute file paths to search."""
    files: list[str] = []
    for path in paths:
        abs_path = vfs.resolve_path(path)
        if vfs.is_file(abs_path):
            files.append(abs_path)
        elif vfs.is_dir(abs_path):
            if not recursive:
                raise CommandError(f"grep: {path}: Is a directory")
            for dirpath, _dirs, filenames in vfs.walk(abs_path):
                for fname in filenames:
                    fpath = dirpath.rstrip("/") + "/" + fname
                    files.append(fpath)
        else:
            raise CommandError(f"grep: {path}: No such file or directory")
    return sorted(set(files))


def cmd_grep(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Search file contents for lines matching a regular expression."""
    parser = _make_parser("grep", "Search for patterns in files")
    parser.add_argument("pattern", nargs="?", default=None)
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("-e", "--regexp", action="append", dest="patterns")
    parser.add_argument("-F", "--fixed-strings", action="store_true")
    parser.add_argument("-i", "--ignore-case", action="store_true")
    parser.add_argument("-n", "--line-number", action="store_true")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("-l", "--files-with-matches", action="store_true")
    parser.add_argument("-c", "--count", action="store_true")
    parser.add_argument("-v", "--invert-match", action="store_true")
    parser.add_argument("-w", "--word-regexp", action="store_true")
    parser.add_argument("-H", "--with-filename", action="store_true")
    parser.add_argument("-h", "--no-filename", action="store_true")
    parser.add_argument("--include", dest="include")
    parser.add_argument("--exclude", dest="exclude")
    parser.add_argument("-A", "--after-context", type=int, default=0)
    parser.add_argument("-B", "--before-context", type=int, default=0)
    parser.add_argument("-C", "--context", type=int, default=0)

    opts = parser.parse_args(args)

    # Build the list of raw patterns from -e flags and/or positional arg
    raw_patterns: list[str] = []
    if opts.patterns:
        raw_patterns.extend(opts.patterns)
    if opts.pattern is not None and not opts.patterns:
        raw_patterns.append(opts.pattern)
    if not raw_patterns:
        raise CommandError("grep: no pattern specified")

    if opts.fixed_strings:
        raw_patterns = [re.escape(p) for p in raw_patterns]

    if opts.word_regexp:
        raw_patterns = [r"\b(?:" + p + r")\b" for p in raw_patterns]

    combined = "|".join(raw_patterns) if len(raw_patterns) > 1 else raw_patterns[0]

    if not opts.fixed_strings:
        _check_for_redos(combined)

    after_ctx = max(opts.after_context, opts.context)
    before_ctx = max(opts.before_context, opts.context)

    flags = re.IGNORECASE if opts.ignore_case else 0
    try:
        regex = re.compile(combined, flags)
    except re.error as exc:
        raise CommandError(f"grep: invalid regex: {exc}") from exc

    files = _collect_files(vfs, opts.paths, opts.recursive)

    if opts.include:
        files = [f for f in files if fnmatch.fnmatch(f.rsplit("/", 1)[-1], opts.include)]
    if opts.exclude:
        files = [f for f in files if not fnmatch.fnmatch(f.rsplit("/", 1)[-1], opts.exclude)]

    if opts.no_filename:
        show_prefix = False
    elif opts.with_filename:
        show_prefix = True
    else:
        show_prefix = len(files) > 1

    if opts.files_with_matches:
        matched_files: list[str] = []
        for fpath in files:
            content = vfs.read_file(fpath)
            if _match_lines(regex, content.splitlines(), opts.invert_match):
                matched_files.append(fpath)
        return "\n".join(matched_files)

    if opts.count:
        parts: list[str] = []
        for fpath in files:
            content = vfs.read_file(fpath)
            n = len(_match_lines(regex, content.splitlines(), opts.invert_match))
            if show_prefix:
                parts.append(f"{fpath}:{n}")
            else:
                parts.append(str(n))
        return "\n".join(parts)

    # Full matching with optional context
    has_context = before_ctx > 0 or after_ctx > 0
    output_lines: list[str] = []
    first_file = True

    for fpath in files:
        content = vfs.read_file(fpath)
        lines = content.splitlines()

        match_indices = _match_lines(regex, lines, opts.invert_match)

        if not match_indices:
            continue

        context_groups: list[tuple[int, int]] = []
        for idx in sorted(match_indices):
            start = max(0, idx - before_ctx)
            end = min(len(lines) - 1, idx + after_ctx)
            if context_groups and start <= context_groups[-1][1] + 1:
                context_groups[-1] = (context_groups[-1][0], end)
            else:
                context_groups.append((start, end))

        if not first_file and has_context:
            output_lines.append("--")
        first_file = False

        for gi, (gstart, gend) in enumerate(context_groups):
            if gi > 0 and has_context:
                output_lines.append("--")
            for idx in range(gstart, gend + 1):
                is_match = idx in match_indices
                sep = ":" if is_match else "-"
                parts_line: list[str] = []
                if show_prefix:
                    parts_line.append(fpath)
                    parts_line.append(sep)
                if opts.line_number:
                    parts_line.append(str(idx + 1))
                    parts_line.append(sep)
                parts_line.append(lines[idx])
                output_lines.append("".join(parts_line))

    return "\n".join(output_lines)


# ------------------------------------------------------------------
# find
# ------------------------------------------------------------------

def cmd_find(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Find files and directories matching given criteria."""
    parser = _make_parser("find", "Search for files in a directory hierarchy")
    parser.add_argument("start", nargs="?", default=".")
    parser.add_argument("-name", dest="name")
    parser.add_argument("-iname", dest="iname")
    parser.add_argument("-type", dest="type", choices=["f", "d"])
    parser.add_argument("-path", dest="path_pattern")
    parser.add_argument("-maxdepth", dest="maxdepth", type=int)
    parser.add_argument("-mindepth", dest="mindepth", type=int)
    parser.add_argument("--not-name", dest="not_name")
    parser.add_argument("--not-path", dest="not_path")

    opts = parser.parse_args(args)

    start = opts.start
    abs_start = vfs.resolve_path(start)

    if not vfs.is_dir(abs_start):
        if vfs.exists(abs_start):
            raise CommandError(f"find: '{start}': Not a directory")
        raise CommandError(f"find: '{start}': No such file or directory")

    use_relative = not start.startswith("/")
    results: list[str] = []

    def _display_path(abs_path: str) -> str:
        if abs_path == abs_start:
            return start if use_relative else abs_path
        if abs_start == "/":
            rel = abs_path
        else:
            rel = abs_path[len(abs_start):]
        if use_relative:
            return start.rstrip("/") + rel
        return abs_path

    def _depth(abs_path: str) -> int:
        if abs_path == abs_start:
            return 0
        if abs_start == "/":
            return abs_path.count("/")
        return abs_path[len(abs_start):].count("/")

    def _matches(display: str, basename: str, entry_type: str, depth: int) -> bool:
        if opts.maxdepth is not None and depth > opts.maxdepth:
            return False
        if opts.mindepth is not None and depth < opts.mindepth:
            return False
        if opts.type is not None and opts.type != entry_type:
            return False
        if opts.name is not None and not fnmatch.fnmatch(basename, opts.name):
            return False
        if opts.iname is not None and not fnmatch.fnmatch(basename.lower(), opts.iname.lower()):
            return False
        if opts.path_pattern is not None and not fnmatch.fnmatch(display, opts.path_pattern):
            return False
        if opts.not_name is not None and fnmatch.fnmatch(basename, opts.not_name):
            return False
        if opts.not_path is not None and fnmatch.fnmatch(display, opts.not_path):
            return False
        return True

    for dirpath, dirnames, filenames in vfs.walk(abs_start):
        dir_depth = _depth(dirpath)

        if opts.maxdepth is not None and dir_depth > opts.maxdepth:
            continue

        dp = _display_path(dirpath)
        basename = dirpath.rsplit("/", 1)[-1] if dirpath != "/" else "/"
        if _matches(dp, basename, "d", dir_depth):
            results.append(dp)

        if opts.maxdepth is not None and dir_depth + 1 > opts.maxdepth:
            continue

        for fname in filenames:
            fpath = dirpath.rstrip("/") + "/" + fname
            fdp = _display_path(fpath)
            fdepth = dir_depth + 1
            if _matches(fdp, fname, "f", fdepth):
                results.append(fdp)

    return "\n".join(sorted(results))

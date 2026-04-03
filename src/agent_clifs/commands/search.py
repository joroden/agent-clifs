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
    parser.add_argument("-r", "-R", "--recursive", action="store_true")
    parser.add_argument("-l", "--files-with-matches", action="store_true")
    parser.add_argument("-L", "--files-without-match", action="store_true")
    parser.add_argument("-c", "--count", action="store_true")
    parser.add_argument("-v", "--invert-match", action="store_true")
    parser.add_argument("-w", "--word-regexp", action="store_true")
    parser.add_argument("-x", "--line-regexp", action="store_true")
    parser.add_argument("-o", "--only-matching", action="store_true")
    parser.add_argument("-q", "--quiet", "--silent", action="store_true")
    parser.add_argument("-s", "--no-messages", action="store_true")
    parser.add_argument("-m", "--max-count", type=int, default=None, metavar="N")
    parser.add_argument("-H", "--with-filename", action="store_true")
    parser.add_argument("-h", "--no-filename", action="store_true")
    parser.add_argument("--include", dest="include")
    parser.add_argument("--exclude", dest="exclude")
    parser.add_argument("-A", "--after-context", type=int, default=0)
    parser.add_argument("-B", "--before-context", type=int, default=0)
    parser.add_argument("-C", "--context", type=int, default=0)
    # Regex-engine selection flags: Python re is already ERE/PCRE-like; accepted for
    # compatibility so combined flags like -Ern or -Prn work without errors.
    parser.add_argument("-E", "--extended-regexp", action="store_true")
    parser.add_argument("-G", "--basic-regexp", action="store_true")
    parser.add_argument("-P", "--perl-regexp", action="store_true")

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

    if opts.line_regexp:
        raw_patterns = [r"^(?:" + p + r")$" for p in raw_patterns]

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

    try:
        files = _collect_files(vfs, opts.paths, opts.recursive)
    except CommandError:
        if opts.no_messages:
            return ""
        raise

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

    # -L: files WITHOUT any match (complement of -l)
    if opts.files_without_match:
        result: list[str] = []
        for fpath in files:
            content = vfs.read_file(fpath)
            if not _match_lines(regex, content.splitlines(), opts.invert_match):
                result.append(fpath)
        return "\n".join(result)

    # -l: files that contain at least one match
    if opts.files_with_matches:
        matched_files: list[str] = []
        for fpath in files:
            content = vfs.read_file(fpath)
            if _match_lines(regex, content.splitlines(), opts.invert_match):
                matched_files.append(fpath)
        return "\n".join(matched_files)

    # -c: count matching lines per file
    if opts.count:
        parts: list[str] = []
        for fpath in files:
            content = vfs.read_file(fpath)
            n = len(_match_lines(regex, content.splitlines(), opts.invert_match))
            if opts.max_count is not None:
                n = min(n, opts.max_count)
            if show_prefix:
                parts.append(f"{fpath}:{n}")
            else:
                parts.append(str(n))
        return "\n".join(parts)

    # -q: suppress all output regardless of match result
    if opts.quiet:
        return ""

    # Full matching with optional context / only-matching
    has_context = before_ctx > 0 or after_ctx > 0
    output_lines: list[str] = []
    first_file = True

    for fpath in files:
        content = vfs.read_file(fpath)
        lines = content.splitlines()

        match_indices = _match_lines(regex, lines, opts.invert_match)

        if not match_indices:
            continue

        sorted_matches = sorted(match_indices)

        # -m: cap the number of matching lines per file
        if opts.max_count is not None:
            sorted_matches = sorted_matches[: opts.max_count]
            match_indices = set(sorted_matches)

        # -o: emit only the matched text portions, one per match per line
        if opts.only_matching and not opts.invert_match:
            for idx in sorted_matches:
                for m in regex.finditer(lines[idx]):
                    parts_line: list[str] = []
                    if show_prefix:
                        parts_line.append(fpath + ":")
                    if opts.line_number:
                        parts_line.append(str(idx + 1) + ":")
                    parts_line.append(m.group())
                    output_lines.append("".join(parts_line))
            continue

        context_groups: list[tuple[int, int]] = []
        for idx in sorted_matches:
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
                parts_line = []
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
# find – expression-parser helpers
# ------------------------------------------------------------------

# Tokens that signal the start of a find expression (vs. a starting path).
_FIND_EXPR_TOKENS: frozenset[str] = frozenset({
    "-name", "-iname", "-type", "-path", "-maxdepth", "-mindepth",
    "-size", "-empty", "-newer", "-print", "-delete", "-exec",
    "-not", "-a", "-and", "-o", "-or", "!", "(", ")"
})


def _make_size_pred(spec: str, vfs: "VirtualFileSystem"):  # type: ignore[return]
    """Return a predicate function for ``-size SPEC`` (e.g. ``+5k``, ``-10M``)."""
    m = re.match(r"^([+-]?)(\d+)([cwbkMG]?)$", spec)
    if not m:
        raise CommandError(f"find: -size: invalid size spec '{spec}'")
    cmp_op, num_s, unit = m.groups()
    num = int(num_s)
    unit_bytes: dict[str, int] = {
        "": 512, "b": 512, "c": 1, "w": 2,
        "k": 1024, "M": 1024 * 1024, "G": 1024 * 1024 * 1024,
    }
    factor = unit_bytes[unit]

    def _pred(abs_p: str, t: str, dp: str, bn: str) -> bool:
        if t != "f":
            return False
        try:
            size = len(vfs.read_file(abs_p).encode())
        except Exception:
            return False
        # Convert bytes to blocks; ceil-divide for block-based units
        n = -(-size // factor) if factor > 1 else size  # ceil div
        if cmp_op == "+":
            return n > num
        if cmp_op == "-":
            return n < num
        return n == num

    return _pred


class _FindParser:
    """Recursive-descent parser for ``find`` predicate expressions.

    Grammar::

        expr    = or
        or      = and ( ('-o' | '-or') and )*
        and     = not  ( ('-a' | '-and' | <implicit>) not )*
        not     = ('!' | '-not') not | primary
        primary = '(' expr ')' | predicate | action
    """

    def __init__(self, vfs: "VirtualFileSystem", tokens: list[str]) -> None:
        self.vfs = vfs
        self.tokens: list[str] = list(tokens)
        self.pos = 0
        self.maxdepth: int | None = None
        self.mindepth: int | None = None
        self.has_delete = False
        self._hoist_depth_options()

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------

    def _hoist_depth_options(self) -> None:
        """-maxdepth / -mindepth are global options; pull them out early."""
        remaining: list[str] = []
        i = 0
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok in ("-maxdepth", "-mindepth") and i + 1 < len(self.tokens):
                try:
                    val = int(self.tokens[i + 1])
                except ValueError:
                    raise CommandError(
                        f"find: {tok}: invalid number '{self.tokens[i + 1]}'"
                    )
                if tok == "-maxdepth":
                    self.maxdepth = val
                else:
                    self.mindepth = val
                i += 2
            else:
                remaining.append(self.tokens[i])
                i += 1
        self.tokens = remaining

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    @property
    def _cur(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _need(self, flag: str) -> str:
        if self.pos >= len(self.tokens):
            raise CommandError(f"find: missing argument to '{flag}'")
        return self._advance()

    # ------------------------------------------------------------------
    # Grammar rules
    # ------------------------------------------------------------------

    def parse(self):
        if self.pos >= len(self.tokens):
            return lambda *_: True  # empty expression → match everything
        pred = self._or()
        if self.pos < len(self.tokens):
            raise CommandError(f"find: unexpected token '{self.tokens[self.pos]}'")
        return pred

    def _or(self):
        left = self._and()
        while self._cur in ("-o", "-or"):
            self._advance()
            right = self._and()
            left = self._mk_or(left, right)
        return left

    def _and(self):
        left = self._not()
        while self._cur not in (None, "-o", "-or", ")"):
            if self._cur in ("-a", "-and"):
                self._advance()
            right = self._not()
            left = self._mk_and(left, right)
        return left

    def _not(self):
        if self._cur in ("!", "-not"):
            self._advance()
            return self._mk_not(self._not())
        return self._primary()

    def _primary(self):  # noqa: C901
        tok = self._cur
        if tok is None:
            return lambda *_: True

        if tok == "(":
            self._advance()
            inner = self._or()
            if self._cur == ")":
                self._advance()
            else:
                raise CommandError("find: unmatched '('")
            return inner

        self._advance()  # consume the predicate token

        if tok == "-name":
            pat = self._need("-name")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(bn, p)

        if tok == "-iname":
            pat = self._need("-iname")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(bn.lower(), p.lower())

        if tok == "-type":
            tv = self._need("-type")
            if tv not in ("f", "d"):
                raise CommandError(f"find: -type: unknown type '{tv}'; use 'f' or 'd'")
            return lambda a, t, d, bn, v=tv: t == v

        if tok == "-path":
            pat = self._need("-path")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(d, p)

        if tok == "-size":
            return _make_size_pred(self._need("-size"), self.vfs)

        if tok == "-empty":
            vfs = self.vfs
            return lambda a, t, d, bn: (
                (t == "f" and _safe_read(vfs, a) == "")
                or (t == "d" and len(vfs.list_dir(a)) == 0)
            )

        if tok == "-newer":
            self._need("-newer")  # consume the ref-path argument
            raise CommandError("find: -newer: not supported (VFS has no timestamps)")

        if tok == "-exec":
            raise CommandError(
                "find: -exec is not supported in VFS context; "
                "pipe find output to other commands instead"
            )

        if tok == "-print":
            return lambda *_: True  # default action; always true

        if tok == "-delete":
            self.has_delete = True
            return lambda *_: True  # deletion is handled after the walk

        raise CommandError(f"find: unknown predicate '{tok}'")

    # ------------------------------------------------------------------
    # Combinator helpers (capture by default arg to avoid late-binding)
    # ------------------------------------------------------------------

    @staticmethod
    def _mk_or(l, r):
        return lambda a, t, d, bn, lp=l, rp=r: lp(a, t, d, bn) or rp(a, t, d, bn)

    @staticmethod
    def _mk_and(l, r):
        return lambda a, t, d, bn, lp=l, rp=r: lp(a, t, d, bn) and rp(a, t, d, bn)

    @staticmethod
    def _mk_not(inner):
        return lambda a, t, d, bn, i=inner: not i(a, t, d, bn)


def _safe_read(vfs: "VirtualFileSystem", path: str) -> str:
    try:
        return vfs.read_file(path)
    except Exception:
        return ""


# ------------------------------------------------------------------
# find
# ------------------------------------------------------------------

def cmd_find(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Find files and directories matching given criteria."""
    # Split leading positional arguments (starting paths) from the expression.
    paths: list[str] = []
    i = 0
    while i < len(args) and args[i] not in _FIND_EXPR_TOKENS:
        paths.append(args[i])
        i += 1
    if not paths:
        paths = ["."]

    fp = _FindParser(vfs, args[i:])
    predicate = fp.parse()

    results: list[str] = []
    to_delete: list[str] = []

    for start in paths:
        abs_start = vfs.resolve_path(start)
        if not vfs.is_dir(abs_start):
            if vfs.exists(abs_start):
                raise CommandError(f"find: '{start}': Not a directory")
            raise CommandError(f"find: '{start}': No such file or directory")

        use_rel = not start.startswith("/")

        def _disp(p: str, _a=abs_start, _s=start, _r=use_rel) -> str:
            if p == _a:
                return _s if _r else p
            suffix = p[len(_a):] if _a != "/" else p
            return (_s.rstrip("/") + suffix) if _r else p

        def _depth(p: str, _a=abs_start) -> int:
            if p == _a:
                return 0
            seg = p[len(_a):] if _a != "/" else p
            return seg.count("/")

        for dirpath, _dirnames, filenames in vfs.walk(abs_start):
            ddepth = _depth(dirpath)

            if fp.maxdepth is not None and ddepth > fp.maxdepth:
                continue

            # Evaluate this directory entry
            if fp.mindepth is None or ddepth >= fp.mindepth:
                dp = _disp(dirpath)
                bn = dirpath.rsplit("/", 1)[-1] if dirpath != "/" else "/"
                if predicate(dirpath, "d", dp, bn):
                    results.append(dp)
                    if fp.has_delete:
                        to_delete.append(dirpath)

            # Evaluate files inside this directory
            if fp.maxdepth is None or ddepth + 1 <= fp.maxdepth:
                for fname in filenames:
                    fpath = dirpath.rstrip("/") + "/" + fname
                    fdepth = ddepth + 1
                    if fp.mindepth is None or fdepth >= fp.mindepth:
                        fdp = _disp(fpath)
                        if predicate(fpath, "f", fdp, fname):
                            results.append(fdp)
                            if fp.has_delete:
                                to_delete.append(fpath)

    if fp.has_delete:
        # Delete files first, then directories deepest-first to avoid conflicts
        for p in [p for p in to_delete if vfs.is_file(p)]:
            try:
                vfs.remove_file(p)
            except Exception:
                pass
        for p in sorted((p for p in to_delete if vfs.is_dir(p)), reverse=True):
            try:
                vfs.rmdir(p, recursive=True)
            except Exception:
                pass
        return ""

    return "\n".join(sorted(results))

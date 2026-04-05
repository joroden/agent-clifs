"""grep command for the virtual filesystem."""

from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING

from agent_clifs.commands._parser import make_parser
from agent_clifs.exceptions import CommandError

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem


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


def _normalize_bre_escapes(pattern: str) -> str:
    """Translate BRE metacharacter escapes to Python *re* (ERE-like) syntax.

    Real grep defaults to BRE where ``\\|``, ``\\+``, ``\\?``, ``\\(``, and
    ``\\)`` are the special operators.  Python's *re* uses ERE-style syntax
    where those operators are written without the leading backslash.  An LLM
    that generates BRE-style patterns will produce patterns that compile but
    match incorrectly (or not at all) in Python *re* without this step.

    ``\\\\`` (escaped backslash) is kept intact so literal-backslash patterns
    round-trip correctly.
    """
    result: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "\\" and i + 1 < len(pattern):
            next_char = pattern[i + 1]
            if next_char == "\\":
                result.append("\\\\")
                i += 2
            elif next_char in "|+?()":
                # BRE operator — drop the backslash prefix, keep the char
                result.append(next_char)
                i += 2
            else:
                result.append("\\")
                result.append(next_char)
                i += 2
        else:
            result.append(pattern[i])
            i += 1
    return "".join(result)


def _match_lines(regex: re.Pattern[str], lines: list[str], invert: bool) -> set[int]:
    return {i for i, line in enumerate(lines) if bool(regex.search(line)) != invert}


# ------------------------------------------------------------------
# grep
# ------------------------------------------------------------------

_GREP_NOOP_FLAGS: list[tuple[str, ...]] = [
    ("-a", "--text"),
    ("-b", "--byte-offset"),
    ("-D", "--devices"),
    ("-E", "--extended-regexp"),
    ("-G", "--basic-regexp"),
    ("-I",),
    ("-P", "--perl-regexp"),
    ("-T", "--initial-tab"),
    ("-U", "--binary"),
    ("-Z", "--null"),
    ("-z", "--null-data"),
    ("--color", "--colour"),
    ("--line-buffered",),
]


def _collect_files(
    vfs: VirtualFileSystem,
    paths: list[str],
    recursive: bool,
    *,
    max_depth: int | None = None,
    exclude_dirs: list[str] | None = None,
    include_dirs: list[str] | None = None,
    skip_dirs: bool = False,
) -> list[str]:
    """Resolve *paths* into a flat sorted list of absolute file paths to search."""
    files: list[str] = []
    for path in paths:
        abs_path = vfs.resolve_path(path)
        if vfs.is_file(abs_path):
            files.append(abs_path)
        elif vfs.is_dir(abs_path):
            if skip_dirs:
                continue
            if not recursive:
                raise CommandError(f"grep: {path}: Is a directory")
            base_depth = abs_path.count("/")
            for dirpath, dirs, filenames in vfs.walk(abs_path):
                current_depth = dirpath.count("/") - base_depth
                if exclude_dirs:
                    dirs[:] = [
                        d
                        for d in dirs
                        if not any(fnmatch.fnmatch(d, p) for p in exclude_dirs)
                    ]
                if include_dirs:
                    dirs[:] = [
                        d
                        for d in dirs
                        if any(fnmatch.fnmatch(d, p) for p in include_dirs)
                    ]
                if max_depth is not None and current_depth >= max_depth:
                    dirs[:] = []
                for fname in filenames:
                    fpath = dirpath.rstrip("/") + "/" + fname
                    files.append(fpath)
        else:
            raise CommandError(f"grep: {path}: No such file or directory")
    return sorted(set(files))


def cmd_grep(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Search file contents for lines matching a regular expression."""
    parser = make_parser("grep", "Search for patterns in files")
    parser.add_argument("pattern", nargs="?", default=None)
    parser.add_argument("paths", nargs="*", default=None)
    parser.add_argument("-e", "--regexp", action="append", dest="patterns")
    parser.add_argument("-F", "--fixed-strings", action="store_true")
    parser.add_argument("-i", "-y", "--ignore-case", action="store_true")
    parser.add_argument("-n", "--line-number", action="store_true")
    parser.add_argument("-r", "-R", "--recursive", action="store_true")
    parser.add_argument(
        "-d", "--directories", choices=["read", "recurse", "skip"], default="read"
    )
    parser.add_argument(
        "-f", "--file", action="append", dest="pattern_files", metavar="FILE"
    )
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
    parser.add_argument(
        "--include-dir", action="append", dest="include_dirs", metavar="GLOB"
    )
    parser.add_argument(
        "--exclude-dir", action="append", dest="exclude_dirs", metavar="GLOB"
    )
    parser.add_argument(
        "--max-depth", type=int, default=None, dest="max_depth", metavar="N"
    )
    parser.add_argument("-A", "--after-context", type=int, default=0)
    parser.add_argument("-B", "--before-context", type=int, default=0)
    parser.add_argument("-C", "--context", type=int, default=0)
    for _noop in _GREP_NOOP_FLAGS:
        has_short = any(len(f) == 2 and f[0] == "-" and f[1] != "-" for f in _noop)
        if has_short:
            parser.add_argument(*_noop, action="store_true")
        else:
            parser.add_argument(*_noop, nargs="?", const=True, default=None)

    opts = parser.parse_args(args)

    if opts.directories == "recurse":
        opts.recursive = True
    skip_dirs = opts.directories == "skip"

    # When patterns come from -e/-f, argparse may assign the first bare path
    # argument to opts.pattern instead of opts.paths. Move it over.
    if (opts.patterns or opts.pattern_files) and opts.pattern is not None:
        opts.paths = [opts.pattern] + (opts.paths or [])
        opts.pattern = None
    if not opts.paths:
        opts.paths = ["."]

    # Build the list of raw patterns from -e flags, -f files, and/or positional arg
    raw_patterns: list[str] = []
    if opts.patterns:
        raw_patterns.extend(opts.patterns)
    if opts.pattern_files:
        for fpath in opts.pattern_files:
            abs_fpath = vfs.resolve_path(fpath)
            try:
                raw_patterns.extend(
                    line for line in vfs.read_file(abs_fpath).splitlines() if line
                )
            except Exception:
                raise CommandError(f"grep: {fpath}: No such file or directory")
    if opts.pattern is not None and not opts.patterns and not opts.pattern_files:
        raw_patterns.append(opts.pattern)
    if not raw_patterns:
        raise CommandError("grep: no pattern specified")

    # Save originals before transformation for BM25 token extraction.
    original_patterns = list(raw_patterns)

    if opts.fixed_strings:
        raw_patterns = [re.escape(p) for p in raw_patterns]
    else:
        raw_patterns = [_normalize_bre_escapes(p) for p in raw_patterns]

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
        files = _collect_files(
            vfs,
            opts.paths,
            opts.recursive,
            max_depth=opts.max_depth,
            exclude_dirs=opts.exclude_dirs,
            include_dirs=opts.include_dirs,
            skip_dirs=skip_dirs,
        )
    except CommandError:
        if opts.no_messages:
            return ""
        raise

    if opts.include:
        files = [
            f for f in files if fnmatch.fnmatch(f.rsplit("/", 1)[-1], opts.include)
        ]
    if opts.exclude:
        files = [
            f for f in files if not fnmatch.fnmatch(f.rsplit("/", 1)[-1], opts.exclude)
        ]

    # BM25 pre-filtering: when the VFS carries a ranking index, score all
    # candidate files and keep only the top-N most relevant ones before
    # running the actual regex search.
    if vfs._bm25_index is not None and files:
        from agent_clifs.bm25 import extract_query_tokens

        query_tokens: list[str] = []
        for p in original_patterns:
            query_tokens.extend(extract_query_tokens(p, fixed_string=opts.fixed_strings))
        if query_tokens:
            files = vfs._bm25_index.top_files(query_tokens, files, vfs._bm25_top_n)

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

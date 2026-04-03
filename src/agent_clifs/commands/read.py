"""File reading commands: cat, head, tail, wc, sed."""

from __future__ import annotations

import argparse
import re
from typing import TYPE_CHECKING

from agent_clifs.exceptions import CommandError, VFSError

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem


class _ErrorRaisingParser(argparse.ArgumentParser):
    """ArgumentParser that raises CommandError instead of calling sys.exit."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise CommandError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if status:
            raise CommandError(message or f"{self.prog}: exit {status}")
        raise CommandError(message or "")


def _make_parser(prog: str, description: str) -> _ErrorRaisingParser:
    return _ErrorRaisingParser(prog=prog, description=description, add_help=False)


def _read(vfs: VirtualFileSystem, path: str, cmd: str) -> str:
    """Read a file, translating VFS exceptions into CommandError."""
    try:
        return vfs.read_file(path)
    except VFSError as exc:
        raise CommandError(f"{cmd}: {exc}") from exc


# ------------------------------------------------------------------
# cat
# ------------------------------------------------------------------


def cmd_cat(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Concatenate and print files."""
    parser = _make_parser("cat", "Concatenate and print files")
    parser.add_argument("-n", "--number", action="store_true", help="number all output lines")
    parser.add_argument("-b", "--number-nonblank", action="store_true",
                        help="number non-empty output lines (overrides -n)")
    parser.add_argument("-s", "--squeeze-blank", action="store_true", help="suppress repeated empty lines")
    parser.add_argument("files", nargs="+", metavar="FILE")
    parsed = parser.parse_args(args)

    contents: list[str] = [_read(vfs, f, "cat") for f in parsed.files]
    combined = "".join(contents)

    if parsed.squeeze_blank:
        lines = combined.splitlines(keepends=True)
        squeezed: list[str] = []
        prev_blank = False
        for line in lines:
            is_blank = line.strip() == ""
            if is_blank and prev_blank:
                continue
            squeezed.append(line)
            prev_blank = is_blank
        combined = "".join(squeezed)

    # -b overrides -n: number only non-blank lines
    if parsed.number_nonblank:
        lines = combined.splitlines(keepends=True)
        counter = 0
        result: list[str] = []
        for line in lines:
            if line.rstrip("\r\n"):  # non-blank
                counter += 1
                result.append(f"{counter:6}\t{line}")
            else:
                result.append(line)
        return "".join(result)

    if not parsed.number:
        return combined

    lines = combined.splitlines(keepends=True)
    numbered = [f"{i + 1:6}\t{line}" for i, line in enumerate(lines)]
    return "".join(numbered)


# ------------------------------------------------------------------
# head
# ------------------------------------------------------------------


def cmd_head(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Display the first lines of files."""
    parser = _make_parser("head", "Display the first lines of a file")
    parser.add_argument("-n", "--lines", type=int, default=10, metavar="N")
    parser.add_argument("-c", "--bytes", type=int, default=None, metavar="N",
                        help="print the first N bytes")
    parser.add_argument("files", nargs="+", metavar="FILE")
    parsed = parser.parse_args(args)

    multiple = len(parsed.files) > 1
    parts: list[str] = []

    for i, filepath in enumerate(parsed.files):
        content = _read(vfs, filepath, "head")
        if parsed.bytes is not None:
            selected_text = content[: parsed.bytes]
        else:
            selected_text = "".join(content.splitlines(keepends=True)[: parsed.lines])
        if multiple:
            if i > 0:
                parts.append("\n")
            parts.append(f"==> {filepath} <==\n")
        parts.append(selected_text)

    return "".join(parts)


# ------------------------------------------------------------------
# tail
# ------------------------------------------------------------------


def cmd_tail(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Display the last lines of files."""
    parser = _make_parser("tail", "Display the last lines of a file")
    parser.add_argument("-n", "--lines", default="10", metavar="N",
                        help="number of lines (or +N to start from line N)")
    parser.add_argument("-c", "--bytes", type=int, default=None, metavar="N",
                        help="print the last N bytes")
    parser.add_argument("files", nargs="+", metavar="FILE")
    parsed = parser.parse_args(args)

    from_start = False
    if isinstance(parsed.lines, str) and parsed.lines.startswith("+"):
        from_start = True
        try:
            line_val = int(parsed.lines[1:])
        except ValueError:
            raise CommandError(f"tail: invalid number of lines: '{parsed.lines}'")
    else:
        try:
            line_val = int(parsed.lines)
        except ValueError:
            raise CommandError(f"tail: invalid number of lines: '{parsed.lines}'")

    multiple = len(parsed.files) > 1
    parts: list[str] = []

    for i, filepath in enumerate(parsed.files):
        content = _read(vfs, filepath, "tail")
        if parsed.bytes is not None:
            selected_text = content[-parsed.bytes:] if parsed.bytes else ""
        elif from_start:
            all_lines = content.splitlines(keepends=True)
            selected_text = "".join(all_lines[line_val - 1:]) if line_val >= 1 else "".join(all_lines)
        else:
            all_lines = content.splitlines(keepends=True)
            selected_text = "".join(all_lines[-line_val:]) if line_val else ""
        if multiple:
            if i > 0:
                parts.append("\n")
            parts.append(f"==> {filepath} <==\n")
        parts.append(selected_text)

    return "".join(parts)


# ------------------------------------------------------------------
# wc
# ------------------------------------------------------------------


def cmd_wc(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Print newline, word, and byte counts for files."""
    parser = _make_parser("wc", "Print newline, word, and byte counts")
    parser.add_argument("-l", "--lines", action="store_true", help="print the newline counts")
    parser.add_argument("-w", "--words", action="store_true", help="print the word counts")
    parser.add_argument("-c", "--bytes", action="store_true", help="print the byte counts")
    parser.add_argument("-m", "--chars", action="store_true", help="print the character counts")
    parser.add_argument("files", nargs="+", metavar="FILE")
    parsed = parser.parse_args(args)

    show_all = not (parsed.lines or parsed.words or parsed.bytes or parsed.chars)

    totals = {"lines": 0, "words": 0, "bytes": 0, "chars": 0}
    output_lines: list[str] = []

    for filepath in parsed.files:
        content = _read(vfs, filepath, "wc")
        line_count = content.count("\n")
        word_count = len(content.split())
        byte_count = len(content.encode())
        char_count = len(content)

        totals["lines"] += line_count
        totals["words"] += word_count
        totals["bytes"] += byte_count
        totals["chars"] += char_count

        output_lines.append(_format_wc(
            line_count, word_count, byte_count, char_count, filepath,
            show_all, parsed.lines, parsed.words, parsed.bytes, parsed.chars,
        ))

    if len(parsed.files) > 1:
        output_lines.append(_format_wc(
            totals["lines"], totals["words"], totals["bytes"], totals["chars"], "total",
            show_all, parsed.lines, parsed.words, parsed.bytes, parsed.chars,
        ))

    return "\n".join(output_lines) + "\n"


def _format_wc(
    lines: int, words: int, bytes_: int, chars: int, name: str,
    show_all: bool, show_l: bool, show_w: bool, show_c: bool, show_m: bool,
) -> str:
    parts: list[str] = []
    if show_all or show_l:
        parts.append(f"{lines:>7}")
    if show_all or show_w:
        parts.append(f"{words:>7}")
    if show_all or show_c:
        parts.append(f"{bytes_:>7}")
    if show_m and not show_all:
        parts.append(f"{chars:>7}")
    return " ".join(parts) + f" {name}"


# ------------------------------------------------------------------
# sed
# ------------------------------------------------------------------

_Addr = tuple
_Cmd = tuple


def _sed_parse_addr(s: str, i: int) -> tuple[_Addr | None, int]:
    if i >= len(s):
        return None, i
    if s[i] == '$':
        return ('last',), i + 1
    if s[i].isdigit():
        j = i
        while j < len(s) and s[j].isdigit():
            j += 1
        return ('line', int(s[i:j])), j
    if s[i] == '/':
        j = i + 1
        while j < len(s) and not (s[j] == '/' and s[j - 1] != '\\'):
            j += 1
        pat = s[i + 1:j].replace('\\/', '/')
        return ('regex', pat), j + 1
    return None, i


def _sed_parse(script: str) -> list[_Cmd]:
    commands: list[_Cmd] = []
    i = 0
    s = script.strip()
    while i < len(s):
        while i < len(s) and s[i] in ' \t;\n':
            i += 1
        if i >= len(s):
            break
        addr1, i = _sed_parse_addr(s, i)
        addr2 = None
        if addr1 is not None and i < len(s) and s[i] == ',':
            addr2, i = _sed_parse_addr(s, i + 1)
        if i >= len(s):
            raise CommandError(f"sed: missing command after address")
        cmd = s[i]
        i += 1
        if cmd not in ('p', 'd', 'q', '='):
            raise CommandError(f"sed: unsupported command: {cmd!r}")
        commands.append((addr1, addr2, cmd))
    return commands


def _sed_addr_matches(
    addr: _Addr,
    lineno: int,
    total: int,
    line: str,
) -> bool:
    if addr[0] == 'line':
        return lineno == addr[1]
    if addr[0] == 'last':
        return lineno == total
    return bool(re.search(addr[1], line))


def _sed_range_matches(
    addr1: _Addr | None,
    addr2: _Addr | None,
    lineno: int,
    total: int,
    line: str,
    state: list[bool],
    idx: int,
) -> bool:
    if addr1 is None:
        return True
    if addr2 is None:
        return _sed_addr_matches(addr1, lineno, total, line)

    # Pure line-number range: stateless
    if addr1[0] == 'line' and addr2[0] == 'line':
        return addr1[1] <= lineno <= addr2[1]
    if addr1[0] == 'line' and addr2[0] == 'last':
        return lineno >= addr1[1]

    # Stateful range (involves regex or mixed)
    if not state[idx]:
        if _sed_addr_matches(addr1, lineno, total, line):
            state[idx] = True
            if addr2[0] == 'line' and lineno >= addr2[1]:
                state[idx] = False
            return True
        return False
    else:
        if _sed_addr_matches(addr2, lineno, total, line):
            state[idx] = False
        return True


def cmd_sed(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Basic stream editor for viewing file content."""
    parser = _make_parser("sed", "Stream editor")
    parser.add_argument("-n", "--quiet", "--silent", action="store_true", dest="quiet")
    parser.add_argument("-e", "--expression", action="append", dest="scripts", metavar="SCRIPT")
    parser.add_argument("positional", nargs="*")

    opts = parser.parse_args(args)
    scripts = list(opts.scripts or [])
    remaining = list(opts.positional)

    if not scripts:
        if not remaining:
            raise CommandError("sed: no script specified")
        scripts.append(remaining.pop(0))

    if not remaining:
        raise CommandError("sed: no input file specified")

    parsed: list[_Cmd] = []
    for script in scripts:
        parsed.extend(_sed_parse(script))

    output: list[str] = []
    for filepath in remaining:
        content = _read(vfs, vfs.resolve_path(filepath), "sed")
        lines = content.splitlines()
        total = len(lines)
        range_state = [False] * len(parsed)

        for lineno, line in enumerate(lines, start=1):
            auto_print = not opts.quiet
            skip_rest = False

            for idx, (addr1, addr2, cmd) in enumerate(parsed):
                if skip_rest:
                    break
                if _sed_range_matches(addr1, addr2, lineno, total, line, range_state, idx):
                    if cmd == 'p':
                        output.append(line)
                    elif cmd == 'd':
                        auto_print = False
                        skip_rest = True
                    elif cmd == 'q':
                        if auto_print:
                            output.append(line)
                        return "\n".join(output)
                    elif cmd == '=':
                        output.append(str(lineno))

            if auto_print and not skip_rest:
                output.append(line)

    return "\n".join(output)

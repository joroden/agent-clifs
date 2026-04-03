"""File reading commands: cat, head, tail, view, wc."""

from __future__ import annotations

import argparse
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
# view
# ------------------------------------------------------------------


def cmd_view(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Display file contents with line numbers and optional line range."""
    if not args:
        raise CommandError("view: missing file operand")

    filepath = args[0]
    content = _read(vfs, filepath, "view")
    lines = content.splitlines()
    total = len(lines)

    start_line = 1
    end_line = total

    if len(args) >= 2:
        try:
            start_line = int(args[1])
        except ValueError:
            raise CommandError(f"view: invalid start line: '{args[1]}'")

    if len(args) >= 3:
        try:
            end_line = int(args[2])
        except ValueError:
            raise CommandError(f"view: invalid end line: '{args[2]}'")
        if end_line == -1:
            end_line = total
    elif len(args) == 2:
        end_line = total

    if start_line < 1:
        raise CommandError(f"view: invalid start line: {start_line}")
    if start_line > total:
        raise CommandError(f"view: line {start_line} is beyond end of file ({total} lines)")
    if end_line < start_line:
        raise CommandError(f"view: end line {end_line} is before start line {start_line}")
    if end_line > total:
        end_line = total

    selected = lines[start_line - 1 : end_line]
    width = len(str(end_line))

    showing_range = not (start_line == 1 and end_line == total)
    if showing_range:
        header = f"File: {filepath} (lines {start_line}-{end_line} of {total})"
    else:
        header = f"File: {filepath} ({total} lines)"

    result_lines = [header]
    for i, line in enumerate(selected, start=start_line):
        result_lines.append(f"{i:>{width}} | {line}")

    return "\n".join(result_lines)


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

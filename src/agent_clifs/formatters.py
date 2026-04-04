"""LLM-optimized output formatter for agent-clifs."""

from __future__ import annotations

import re
from collections import OrderedDict

from agent_clifs.vfs import VirtualFileSystem


_PASSTHROUGH_COMMANDS = frozenset({
    "cat", "head", "tail", "view",
    "pwd", "cd", "mkdir", "touch", "write", "append",
    "rm", "cp", "mv", "help",
})


class LLMFormatter:
    """Transforms standard command output into LLM-optimized format.

    The formatter post-processes command output to be more structured
    and token-efficient for LLM consumption.

    When *commands* is provided, only those commands are formatted;
    all others pass through unchanged.  Pass ``None`` (the default) to
    format every supported command.
    """

    def __init__(self, commands: frozenset[str] | None = None) -> None:
        self._enabled: frozenset[str] | None = commands

    def format(self, command: str, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format command output for LLM consumption."""
        if self._enabled is not None and command not in self._enabled:
            return output

        if command in _PASSTHROUGH_COMMANDS:
            return output

        handler = {
            "ls": self._format_ls,
            "tree": self._format_tree,
            "grep": self._format_grep,
            "find": self._format_find,
            "wc": self._format_wc,
        }.get(command)

        if handler is None:
            return output

        return handler(args, output, vfs)

    # ------------------------------------------------------------------
    # ls
    # ------------------------------------------------------------------

    def _format_ls(self, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format ls output into structured listing."""
        if not output.strip():
            return output

        is_long = "-l" in args

        lines: list[str] = []
        for raw_line in output.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if is_long:
                lines.append(self._format_ls_long_line(line))
            else:
                lines.append(self._format_ls_short_line(line))

        return "\n".join(lines)

    @staticmethod
    def _format_ls_short_line(line: str) -> str:
        if line.endswith("/"):
            return f"[dir] {line.rstrip('/')}"
        return f"[file] {line}"

    @staticmethod
    def _format_ls_long_line(line: str) -> str:
        # Long format: "d  <children>  <name>/" or "f  <size>  <name>"
        match = re.match(r"^(d|f)\s+(\d+)\s+(.+)$", line)
        if not match:
            return line

        entry_type, count_str, name = match.groups()
        if entry_type == "d":
            return f"[dir] {name.rstrip('/')} ({count_str} children)"
        return f"[file] {name} ({count_str} bytes)"

    # ------------------------------------------------------------------
    # tree
    # ------------------------------------------------------------------

    def _format_tree(self, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format tree output as sorted full paths with type and size annotations.
        """
        if not output.strip():
            return output

        raw_lines = output.splitlines()
        if not raw_lines:
            return output

        summary_line: str | None = None

        # The last non-empty line is the summary (e.g. "3 directories, 2 files")
        idx = len(raw_lines) - 1
        while idx >= 0 and not raw_lines[idx].strip():
            idx -= 1
        if idx >= 0 and re.match(r"^\d+\s+director", raw_lines[idx]):
            summary_line = raw_lines[idx].strip()
            tree_lines = raw_lines[:idx]
        else:
            tree_lines = list(raw_lines)

        while tree_lines and not tree_lines[-1].strip():
            tree_lines.pop()

        if not tree_lines:
            return output

        root = tree_lines[0].strip().rstrip("/")

        path_stack: list[str] = [root]
        entries: list[tuple[str, bool]] = []  # (absolute_path, is_dir)

        for line in tree_lines[1:]:
            depth, name = self._parse_tree_line(line)
            is_dir = name.endswith("/")
            clean_name = name.rstrip("/")

            # Pop to the correct parent depth before appending
            while len(path_stack) > depth:
                path_stack.pop()

            parent = path_stack[-1]
            full_path = f"{parent.rstrip('/')}/{clean_name}"

            if is_dir:
                path_stack.append(full_path)

            entries.append((full_path, is_dir))

        entries.sort(key=lambda x: x[0])

        result_lines: list[str] = []
        for full_path, is_dir in entries:
            if is_dir:
                result_lines.append(f"[dir] {full_path}")
            else:
                line_hint = ""
                try:
                    content = vfs.read_file(full_path)
                    n = content.count("\n")
                    if content and not content.endswith("\n"):
                        n += 1
                    line_hint = f"  ({n} lines)"
                except Exception:
                    pass
                result_lines.append(f"[file] {full_path}{line_hint}")

        if summary_line:
            dirs_match = re.search(r"(\d+)\s+director", summary_line)
            files_match = re.search(r"(\d+)\s+file", summary_line)
            dir_count = int(dirs_match.group(1)) if dirs_match else 0
            file_count = int(files_match.group(1)) if files_match else 0
            parts: list[str] = []
            if files_match:
                parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
            if dirs_match:
                parts.append(f"{dir_count} director{'ies' if dir_count != 1 else 'y'}")
            result_lines.append(f"({', '.join(parts)})")

        return "\n".join(result_lines)

    @staticmethod
    def _parse_tree_line(line: str) -> tuple[int, str]:
        """Parse a tree line and return (depth, name)."""
        depth = 0
        pos = 0
        while pos < len(line):
            if line[pos:pos + 4] in ("├── ", "└── "):
                depth += 1
                pos += 4
                break
            elif line[pos:pos + 4] in ("│   ", "    "):
                depth += 1
                pos += 4
            else:
                break

        name = line[pos:].strip()
        return depth, name

    # ------------------------------------------------------------------
    # grep
    # ------------------------------------------------------------------

    def _format_grep(self, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format grep output into grouped matches."""
        if not output.strip():
            return output

        # Detect if -l (files only) or -c (counts) mode — pass through
        if "-l" in args:
            return output
        if "-c" in args:
            return output

        has_context = any(a.startswith(("-A", "-B", "-C")) for a in args)

        groups: OrderedDict[str, list[str]] = OrderedDict()
        current_file: str | None = None

        for line in output.splitlines():
            if line == "--":
                # Group separator in context mode — skip
                continue

            # Match: file:lineno:content  or  file-lineno-content (context)
            # Also handle single-file format: lineno:content  or  lineno-content
            match = re.match(r"^(.+?)([:])(\d+)([:])(.*)$", line)
            context_match = re.match(r"^(.+?)(-)(\d+)(-)(.*)$", line)

            if match:
                filepath, _, lineno, _, content = match.groups()
                groups.setdefault(filepath, [])
                groups[filepath].append(f"  L{lineno}: {content}")
            elif context_match and has_context:
                filepath, _, lineno, _, content = context_match.groups()
                groups.setdefault(filepath, [])
                groups[filepath].append(f"  ~{lineno}: {content}")
            else:
                # Fallback: single-file format (lineno:content)
                single_match = re.match(r"^(\d+)(:)(.*)$", line)
                single_ctx = re.match(r"^(\d+)(-)(.*)$", line)
                if single_match:
                    lineno, _, content = single_match.groups()
                    key = ""
                    groups.setdefault(key, [])
                    groups[key].append(f"  L{lineno}: {content}")
                elif single_ctx and has_context:
                    lineno, _, content = single_ctx.groups()
                    key = ""
                    groups.setdefault(key, [])
                    groups[key].append(f"  ~{lineno}: {content}")
                else:
                    # Unknown format, pass through
                    groups.setdefault("", [])
                    groups[""].append(f"  {line}")

        result_lines: list[str] = []
        for filepath, entries in groups.items():
            if filepath:
                result_lines.append(f"[{filepath}]")
            result_lines.extend(entries)

        return "\n".join(result_lines)

    # ------------------------------------------------------------------
    # find
    # ------------------------------------------------------------------

    def _format_find(self, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format find output with type annotations."""
        if not output.strip():
            return output

        lines: list[str] = []
        for raw_line in output.splitlines():
            path = raw_line.strip()
            if not path:
                continue

            resolved = vfs.resolve_path(path)
            if vfs.is_file(resolved):
                lines.append(f"[file] {path}")
            elif vfs.is_dir(resolved):
                lines.append(f"[dir] {path}")
            else:
                lines.append(path)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # wc
    # ------------------------------------------------------------------

    def _format_wc(self, args: list[str], output: str, vfs: VirtualFileSystem) -> str:
        """Format wc output with labeled values."""
        if not output.strip():
            return output

        active_flags = [a for a in args if a.startswith("-")]
        show_lines = "-l" in active_flags
        show_words = "-w" in active_flags
        show_bytes = "-c" in active_flags
        show_all = not (show_lines or show_words or show_bytes)

        result_lines: list[str] = []
        for raw_line in output.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split()
            if not parts:
                continue

            name = parts[-1]
            values = parts[:-1]

            labels: list[str] = []
            if show_all:
                if len(values) >= 3:
                    labels.append(f"{int(values[0])} lines")
                    labels.append(f"{int(values[1])} words")
                    labels.append(f"{int(values[2])} bytes")
            else:
                vi = 0
                if show_lines and vi < len(values):
                    labels.append(f"{int(values[vi])} lines")
                    vi += 1
                if show_words and vi < len(values):
                    labels.append(f"{int(values[vi])} words")
                    vi += 1
                if show_bytes and vi < len(values):
                    labels.append(f"{int(values[vi])} bytes")
                    vi += 1

            if labels:
                result_lines.append(f"{name}: {', '.join(labels)}")
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

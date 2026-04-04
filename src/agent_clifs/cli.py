"""CLI dispatcher for agent-clifs."""

from __future__ import annotations

import shlex
import uuid
from collections.abc import Callable

from agent_clifs._io import RedirectInfo, extract_redirection, split_pipes, strip_pipe_path
from agent_clifs.commands import COMMANDS
from agent_clifs.exceptions import CommandError, VFSError
from agent_clifs.formatters import LLMFormatter
from agent_clifs.vfs import VirtualFileSystem

WRITE_COMMANDS: frozenset[str] = frozenset(
    {"mkdir", "touch", "write", "append", "rm", "cp", "mv"}
)

COMMAND_HELP: dict[str, str] = {
    "pwd": "Print the current working directory",
    "cd": "Change the current working directory",
    "ls": "List directory contents",
    "tree": "Display directory tree structure",
    "cat": "Display file contents",
    "head": "Display first lines of a file",
    "tail": "Display last lines of a file",
    "sed": "Stream editor: print/filter lines by address or pattern",
    "wc": "Count lines, words, and bytes",
    "grep": "Search file contents using regex patterns",
    "find": "Find files and directories by name or type",
    "mkdir": "Create directories",
    "touch": "Create empty files",
    "write": "Write content to a file",
    "append": "Append content to a file",
    "rm": "Remove files or directories",
    "cp": "Copy files or directories",
    "mv": "Move or rename files or directories",
}

_CATEGORIES: dict[str, list[str]] = {
    "Navigation": ["pwd", "cd", "ls", "tree"],
    "Reading": ["cat", "head", "tail", "sed", "wc"],
    "Search": ["grep", "find"],
    "File Operations": ["mkdir", "touch", "write", "append", "rm", "cp", "mv"],
}


class AgentCLI:
    """Command-line interface for AI agents to interact with a VFS.

    Usage::

        cli = AgentCLI()
        cli.execute("write /docs/readme.md 'Hello World'")
        result = cli.execute("grep -rn Hello /docs")
        print(result)
    """

    def __init__(
        self,
        vfs: VirtualFileSystem | None = None,
        *,
        structured: bool | set[str] | frozenset[str] = False,
        readonly: bool = False,
        allowed_commands: set[str] | None = None,
        disabled_commands: set[str] | None = None,
    ) -> None:
        """Initialize with an optional existing VFS.

        *structured* controls LLM-optimized output post-processing:

        * ``True`` — apply :class:`~agent_clifs.formatters.LLMFormatter`
          to all supported commands (``ls``, ``tree``, ``grep``,
          ``find``, ``wc``).
        * A :class:`set` of command names — apply formatting only to
          those commands, e.g. ``structured={"tree", "grep"}``.
        * ``False`` (default) — no formatting applied.

        When *readonly* is ``True``, all write commands (mkdir, touch,
        write, append, rm, cp, mv) are disabled.

        *allowed_commands* is a whitelist — only these commands can be
        executed.  *disabled_commands* is a blacklist — these commands
        cannot be executed.  The two options are mutually exclusive.
        """
        if allowed_commands is not None and disabled_commands is not None:
            raise ValueError(
                "allowed_commands and disabled_commands are mutually exclusive"
            )

        all_names = set(COMMANDS)

        if allowed_commands is not None:
            unknown = allowed_commands - all_names
            if unknown:
                raise ValueError(
                    f"unknown command(s) in allowed_commands: {', '.join(sorted(unknown))}"
                )

        if disabled_commands is not None:
            unknown = disabled_commands - all_names
            if unknown:
                raise ValueError(
                    f"unknown command(s) in disabled_commands: {', '.join(sorted(unknown))}"
                )

        # Start from allowed_commands whitelist or full set
        if allowed_commands is not None:
            active = set(allowed_commands)
        elif disabled_commands is not None:
            active = all_names - disabled_commands
        else:
            active = set(all_names)

        # readonly takes precedence: always remove write commands
        if readonly:
            active -= WRITE_COMMANDS

        self._active_commands: dict[str, Callable] = {
            name: COMMANDS[name] for name in active
        }

        self.vfs = vfs or VirtualFileSystem()
        self.structured = structured
        self.readonly = readonly
        if structured is True:
            self._formatter: LLMFormatter | None = LLMFormatter()
        elif structured:  # non-empty set/frozenset
            self._formatter = LLMFormatter(commands=frozenset(structured))
        else:
            self._formatter = None

    # -- pipe helpers --------------------------------------------------

    def _execute_pipeline(self, segments: list[str]) -> str:
        """Execute a multi-command pipeline.

        Each segment's output is written to a temporary VFS file that is
        appended as a file argument to the next segment.  Temp files are
        always cleaned up.
        """
        # Validate segments
        for idx, seg in enumerate(segments):
            if not seg.strip():
                if idx == 0:
                    raise CommandError("syntax error: unexpected '|' at start of command")
                if idx == len(segments) - 1:
                    raise CommandError("syntax error: unexpected '|' at end of command")
                raise CommandError("syntax error: empty command between pipes")

        temp_files: list[str] = []
        try:
            first_seg, _ = extract_redirection(segments[0].strip())
            result = self._execute_single(first_seg)
            for seg in segments[1:]:
                seg_clean, _ = extract_redirection(seg.strip())
                tmp_path = f"/tmp/.pipe_{uuid.uuid4().hex}"
                pipe_content = result if result.endswith("\n") else result + "\n"
                self.vfs.write_file(tmp_path, pipe_content)
                temp_files.append(tmp_path)
                cmd_str = f"{seg_clean.strip()} {tmp_path}"
                result = self._execute_single(cmd_str)
                result = strip_pipe_path(result, tmp_path)
            return result
        finally:
            for path in temp_files:
                try:
                    self.vfs.remove_file(path)
                except VFSError:
                    pass

    # -- public API -----------------------------------------------------

    def execute(self, command: str) -> str:
        """Execute a CLI command string and return the output.

        Supports pipelines: commands separated by unquoted ``|``
        characters are executed left-to-right, with each command's
        output piped to the next via a temporary VFS file.

        Supports output redirection (``>``, ``>>``) on the last
        segment of a pipeline or on a single command.
        """
        segments = split_pipes(command)
        if len(segments) > 1:
            last_seg, redirect = extract_redirection(segments[-1].strip())
            segments[-1] = last_seg
            result = self._execute_pipeline(segments)
        else:
            command_clean, redirect = extract_redirection(command)
            result = self._execute_single(command_clean)

        return self._apply_redirection(result, redirect)

    def _apply_redirection(self, result: str, redirect: RedirectInfo) -> str:
        """Write *result* to the redirect target and return ``""``."""
        if redirect.target_path is None:
            return result

        if redirect.dev_null:
            return ""

        if self.readonly:
            raise CommandError(
                "redirection to file disabled in readonly mode"
            )

        try:
            if redirect.append:
                self.vfs.append_file(redirect.target_path, result)
            else:
                self.vfs.write_file(redirect.target_path, result)
        except VFSError as exc:
            raise CommandError(str(exc)) from exc

        return ""

    def _execute_single(self, command: str) -> str:
        """Execute a single (non-piped) command string."""
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            raise CommandError(f"syntax error: {exc}") from exc

        if not tokens:
            return ""

        name, args = tokens[0], tokens[1:]

        if name == "help":
            return self.help(args[0] if args else None)

        fn = self._active_commands.get(name)
        if fn is None:
            # Distinguish disabled from truly unknown
            if name in COMMANDS:
                if self.readonly and name in WRITE_COMMANDS:
                    raise CommandError(
                        f"command disabled: {name} (readonly mode)"
                    )
                raise CommandError(f"command disabled: {name}")
            available = ", ".join(sorted(self._active_commands))
            raise CommandError(f"unknown command: {name}\nAvailable commands: {available}")

        try:
            result = fn(self.vfs, args)
        except CommandError:
            raise
        except VFSError as exc:
            raise CommandError(str(exc)) from exc

        if self._formatter is not None:
            result = self._formatter.format(name, args, result, self.vfs)
        return result

    def available_commands(self) -> list[str]:
        """Return sorted list of available command names."""
        return sorted(self._active_commands)

    def help(self, command: str | None = None) -> str:
        """Return help text for a specific command or all commands."""
        if command is None:
            lines: list[str] = ["Available commands:\n"]
            for category, cmds in _CATEGORIES.items():
                active_cmds = [c for c in cmds if c in self._active_commands]
                if not active_cmds:
                    continue
                lines.append(f"  {category}:")
                for cmd in active_cmds:
                    desc = COMMAND_HELP.get(cmd, "")
                    lines.append(f"    {cmd:<10} {desc}")
                lines.append("")
            lines.append('Type "help <command>" for detailed usage.')
            return "\n".join(lines)

        if command not in COMMANDS:
            raise CommandError(f"help: unknown command '{command}'")

        if command not in self._active_commands:
            raise CommandError(f"help: command disabled '{command}'")

        # Try calling with --help to get argparse-generated text
        try:
            COMMANDS[command](self.vfs, ["--help"])
        except CommandError as exc:
            msg = str(exc)
            if msg:
                return msg
        return COMMAND_HELP.get(command, f"No help available for '{command}'")

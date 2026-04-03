"""CLI dispatcher for agent-clifs."""

from __future__ import annotations

import shlex
from collections.abc import Callable

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
    "view": "Display file contents with line numbers and optional range",
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
    "Reading": ["cat", "head", "tail", "view", "wc"],
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
        structured: bool = False,
        readonly: bool = False,
        allowed_commands: set[str] | None = None,
        disabled_commands: set[str] | None = None,
    ) -> None:
        """Initialize with an optional existing VFS.

        When *structured* is ``True``, command output is post-processed
        by :class:`~agent_clifs.formatters.LLMFormatter` for cleaner,
        more token-efficient output optimized for LLM consumption.

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
        self._formatter = LLMFormatter() if structured else None

    def execute(self, command: str) -> str:
        """Execute a CLI command string and return the output."""
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

"""CLI dispatcher for agent-clifs."""

from __future__ import annotations

import shlex

from agent_clifs.commands import COMMANDS
from agent_clifs.exceptions import CommandError, VFSError
from agent_clifs.formatters import LLMFormatter
from agent_clifs.vfs import VirtualFileSystem

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
    ) -> None:
        """Initialize with an optional existing VFS.

        When *structured* is ``True``, command output is post-processed
        by :class:`~agent_clifs.formatters.LLMFormatter` for cleaner,
        more token-efficient output optimized for LLM consumption.
        """
        self.vfs = vfs or VirtualFileSystem()
        self.structured = structured
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

        fn = COMMANDS.get(name)
        if fn is None:
            available = ", ".join(sorted(COMMANDS))
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
        return sorted(COMMANDS)

    def help(self, command: str | None = None) -> str:
        """Return help text for a specific command or all commands."""
        if command is None:
            lines: list[str] = ["Available commands:\n"]
            for category, cmds in _CATEGORIES.items():
                lines.append(f"  {category}:")
                for cmd in cmds:
                    desc = COMMAND_HELP.get(cmd, "")
                    lines.append(f"    {cmd:<10} {desc}")
                lines.append("")
            lines.append('Type "help <command>" for detailed usage.')
            return "\n".join(lines)

        if command not in COMMANDS:
            raise CommandError(f"help: unknown command '{command}'")

        # Try calling with --help to get argparse-generated text
        try:
            COMMANDS[command](self.vfs, ["--help"])
        except CommandError as exc:
            msg = str(exc)
            if msg:
                return msg
        return COMMAND_HELP.get(command, f"No help available for '{command}'")

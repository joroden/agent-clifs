from __future__ import annotations

import argparse

from agent_clifs.exceptions import CommandError


class CommandArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises CommandError instead of calling sys.exit."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise CommandError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            raise CommandError(message.strip())
        raise CommandError("")


def make_parser(prog: str, description: str) -> CommandArgumentParser:
    """Return a CommandArgumentParser with help disabled."""
    return CommandArgumentParser(prog=prog, description=description, add_help=False)

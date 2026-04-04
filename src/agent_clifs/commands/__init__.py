"""Command registry for agent-clifs CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_clifs.vfs import VirtualFileSystem

from agent_clifs.commands.file_ops import (
    cmd_append,
    cmd_cp,
    cmd_mkdir,
    cmd_mv,
    cmd_rm,
    cmd_touch,
    cmd_write,
)
from agent_clifs.commands.navigation import cmd_cd, cmd_ls, cmd_pwd, cmd_tree
from agent_clifs.commands.read import cmd_cat, cmd_head, cmd_sed, cmd_tail, cmd_wc
from agent_clifs.commands.find import cmd_find
from agent_clifs.commands.grep import cmd_grep

COMMANDS: dict[str, Callable[[VirtualFileSystem, list[str]], str]] = {
    "pwd": cmd_pwd,
    "cd": cmd_cd,
    "ls": cmd_ls,
    "tree": cmd_tree,
    "cat": cmd_cat,
    "head": cmd_head,
    "tail": cmd_tail,
    "sed": cmd_sed,
    "wc": cmd_wc,
    "grep": cmd_grep,
    "find": cmd_find,
    "mkdir": cmd_mkdir,
    "touch": cmd_touch,
    "write": cmd_write,
    "append": cmd_append,
    "rm": cmd_rm,
    "cp": cmd_cp,
    "mv": cmd_mv,
}

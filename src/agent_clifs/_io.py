"""Pipe and redirection parsing utilities for agent-clifs CLI."""

from __future__ import annotations

from dataclasses import dataclass

from agent_clifs.exceptions import CommandError


@dataclass(frozen=True, slots=True)
class RedirectInfo:
    """Describes an output redirection parsed from a command string."""

    target_path: str | None = None
    append: bool = False
    dev_null: bool = False
    stderr_redirect: str | None = None


def split_pipes(command: str) -> list[str]:
    """Split *command* on unquoted ``|`` characters.

    Characters inside single or double quotes are never treated as
    pipe operators.  Returns a list of raw command strings.
    """
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and not in_single and i + 1 < len(command):
            current.append(ch)
            current.append(command[i + 1])
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "|" and not in_single and not in_double:
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return segments


def extract_redirection(command: str) -> tuple[str, RedirectInfo]:
    """Parse *command* for unquoted redirection operators.

    Returns ``(clean_command, redirect_info)``.  Handles ``>``, ``>>``,
    ``2>``, ``2>>``, with or without spaces before the target path.
    Operators inside single or double quotes are ignored.
    """
    result_parts: list[str] = []
    target_path: str | None = None
    append = False
    dev_null = False
    stderr_redirect: str | None = None

    in_single = False
    in_double = False
    i = 0
    length = len(command)

    while i < length:
        ch = command[i]

        # Handle escape sequences outside single quotes
        if ch == "\\" and not in_single and i + 1 < length:
            result_parts.append(ch)
            result_parts.append(command[i + 1])
            i += 2
            continue

        # Track quoting state
        if ch == "'" and not in_double:
            in_single = not in_single
            result_parts.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            result_parts.append(ch)
            i += 1
            continue

        # Only look for redirects outside quotes
        if in_single or in_double:
            result_parts.append(ch)
            i += 1
            continue

        # Check for stderr redirect: 2>> or 2>
        if ch == "2" and i + 1 < length and command[i + 1] == ">":
            is_append = i + 2 < length and command[i + 2] == ">"
            op_end = i + (3 if is_append else 2)
            j = op_end
            while j < length and command[j] == " ":
                j += 1
            redir_target, j = _read_redirect_target(command, j)
            if redir_target is None:
                raise CommandError("syntax error: missing redirect target")
            stderr_redirect = redir_target
            i = j
            continue

        # Check for stdout redirect: >> or >
        if ch == ">":
            is_append = i + 1 < length and command[i + 1] == ">"
            op_end = i + (2 if is_append else 1)
            j = op_end
            while j < length and command[j] == " ":
                j += 1
            redir_target, j = _read_redirect_target(command, j)
            if redir_target is None:
                raise CommandError("syntax error: missing redirect target")
            target_path = redir_target
            append = is_append
            dev_null = redir_target == "/dev/null"
            i = j
            continue

        result_parts.append(ch)
        i += 1

    info = RedirectInfo(
        target_path=target_path,
        append=append,
        dev_null=dev_null,
        stderr_redirect=stderr_redirect,
    )
    return "".join(result_parts).strip(), info


def _read_redirect_target(command: str, pos: int) -> tuple[str | None, int]:
    """Read a redirect target starting at *pos*, handling quotes."""
    length = len(command)
    if pos >= length:
        return None, pos

    # Quoted target
    if command[pos] in ('"', "'"):
        quote = command[pos]
        pos += 1
        start = pos
        while pos < length and command[pos] != quote:
            pos += 1
        if pos >= length:
            return None, pos  # unterminated quote - let shlex catch it
        target = command[start:pos]
        pos += 1  # skip closing quote
        return target, pos

    # Unquoted target: read until whitespace or end
    start = pos
    while pos < length and command[pos] not in (" ", "\t"):
        pos += 1
    if pos == start:
        return None, pos
    return command[start:pos], pos


def strip_pipe_path(output: str, pipe_path: str) -> str:
    """Remove *pipe_path* prefix/suffix artefacts from grep/find output."""
    prefix = pipe_path + ":"
    suffix = " " + pipe_path
    lines = output.splitlines(keepends=True)
    result = []
    for line in lines:
        body = line.rstrip("\n\r")
        eol = line[len(body) :]
        if body.startswith(prefix):
            body = body[len(prefix) :].lstrip(" ")
        elif body.endswith(suffix):
            body = body[: -len(suffix)]
        result.append(body + eol)
    return "".join(result)

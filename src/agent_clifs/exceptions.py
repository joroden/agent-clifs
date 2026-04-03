"""Exception hierarchy for agent-clifs."""

from __future__ import annotations


class VFSError(Exception):
    """Base exception for all VFS errors."""


class FileNotFoundVFSError(VFSError):
    """Raised when a file or directory is not found."""


class FileExistsVFSError(VFSError):
    """Raised when a file or directory already exists."""


class IsADirectoryVFSError(VFSError):
    """Raised when a file operation is attempted on a directory."""


class NotADirectoryVFSError(VFSError):
    """Raised when a directory operation is attempted on a file."""


class CommandError(VFSError):
    """Raised when a CLI command fails (bad args, etc)."""

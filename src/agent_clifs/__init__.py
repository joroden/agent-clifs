"""agent-clifs - A dictionary-based virtual filesystem with CLI for AI agents."""

from importlib.metadata import PackageNotFoundError, version as _get_version

from agent_clifs.cli import AgentCLI
from agent_clifs.formatters import LLMFormatter
from agent_clifs.vfs import VirtualFileSystem

__all__ = ["AgentCLI", "LLMFormatter", "VirtualFileSystem"]

try:
    __version__ = _get_version("agent-clifs")
except PackageNotFoundError:
    __version__ = "0.0.0"

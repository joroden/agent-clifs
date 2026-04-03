from __future__ import annotations

import pytest
from agent_clifs import AgentCLI, VirtualFileSystem


@pytest.fixture
def vfs():
    """Fresh VFS instance."""
    return VirtualFileSystem()


@pytest.fixture
def populated_vfs():
    """VFS with sample files for testing."""
    fs = VirtualFileSystem()
    fs.load_from_dict({
        "/docs/readme.md": "# Project\n\nWelcome to the project.\n",
        "/docs/api/users.md": "# Users API\n\nGET /api/users\nPOST /api/users\n",
        "/docs/api/auth.md": "# Auth API\n\nPOST /api/auth/login\nPOST /api/auth/logout\n",
        "/src/main.py": "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n",
        "/src/utils.py": "def helper():\n    return 42\n",
        "/src/tests/test_main.py": "def test_main():\n    assert True\n",
    })
    return fs


@pytest.fixture
def cli(populated_vfs):
    """CLI backed by the populated VFS."""
    return AgentCLI(populated_vfs)

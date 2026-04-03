# agent-clifs

**A virtual filesystem for AI agents. Unix commands they already know. Zero dependencies.**

---

Load documents, codebases, or any text into an in-memory filesystem and let your AI agent explore it with `ls`, `grep`, `find`, `tree`, and more.

## Install

```bash
pip install agent-clifs
```

## Quick Start

```python
from agent_clifs import AgentCLI

cli = AgentCLI()

# Load your documentation
cli.execute("mkdir -p /docs/api")
cli.execute("write /docs/api/users.md '# Users API\nGET /users\nPOST /users'")
cli.execute("write /docs/api/auth.md '# Auth API\nPOST /auth/login'")

# An agent explores just like a developer would
cli.execute("tree /docs")              # See the structure
cli.execute("grep -rn 'POST' /docs")   # Search for patterns
cli.execute("view /docs/api/users.md 1 5")  # Read specific lines
```

## Bulk Loading

The most common pattern — load from a dictionary:

```python
from agent_clifs import AgentCLI, VirtualFileSystem

vfs = VirtualFileSystem()
vfs.load_from_dict({
    "/src/app.py": "from flask import Flask\napp = Flask(__name__)",
    "/src/models.py": "class User:\n    ...",
    "/docs/setup.md": "# Setup\nRun `pip install -r requirements.txt`",
})

cli = AgentCLI(vfs)
cli.execute("find /src -name '*.py'")
```

## Use with Any Agent Framework

Just pass `cli.execute` as a tool function:

```python
from langchain.tools import Tool

tool = Tool(
    name="filesystem",
    description="Execute filesystem commands: ls, cat, grep, find, tree, view, head, tail, wc",
    func=cli.execute,
)
```

Works the same way with LlamaIndex, CrewAI, or any framework that accepts a callable.

## LLM-Optimized Mode

Pass `structured=True` for token-efficient output — no box-drawing characters, type-annotated entries, results grouped by file:

```python
cli = AgentCLI(structured=True)
```

```
# grep (standard)                   # grep (structured)
/docs/api/auth.md:3:POST /api/auth   [/docs/api/auth.md]
/docs/api/users.md:3:POST /api/users   L3: POST /api/auth
                                     [/docs/api/users.md]
                                       L3: POST /api/users
```

## Commands

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `ls` | List directory | `-l` `-h` `-R` `-S` `-a` `-d` `-1` |
| `grep` | Search contents | `-r` `-i` `-n` `-l` `-c` `-v` `-w` `-F` `-A`/`-B`/`-C` `--include` `--exclude` |
| `find` | Find files | `-name` `-iname` `-type` `-path` `-maxdepth` `-mindepth` |
| `view` | Read with line range | `view <file> [start] [end]` |
| `cat` | Display files | `-n` `-s` |
| `tree` | Directory tree | `-L` `-d` `-a` |
| `head`/`tail` | First/last lines | `-n` `-c` |
| `wc` | Count lines/words | `-l` `-w` `-c` |
| `mkdir` | Create directory | `-p` `-v` |
| `cp` | Copy | `-r` `-a` `-n` `-v` |
| `mv` | Move/rename | `-n` `-v` |
| `rm` | Remove | `-r` `-f` `-v` |
| `write` | Write to file | `write <path> <content>` |
| `append` | Append to file | `append <path> <content>` |
| `touch` | Create empty file | `-c` |
| `pwd`/`cd` | Navigate | `cd -` `cd ~` |

## Python API

```python
from agent_clifs import VirtualFileSystem

vfs = VirtualFileSystem()
vfs.load_from_dict({"/file.txt": "hello"})  # bulk load
content = vfs.read_file("/file.txt")         # read
vfs.write_file("/new.txt", "world")          # write
snapshot = vfs.to_dict()                     # export {path: content}
```

## Setup for PyPI Publishing

This project uses GitHub Actions with trusted publishing. See `.github/workflows/release.yml`.

## License

[Unlicense](./LICENSE) — public domain.

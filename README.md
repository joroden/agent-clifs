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

# Load your content
cli.execute("mkdir -p /docs/api")
cli.execute("write /docs/api/users.md '# Users API\nGET /users\nPOST /users'")
cli.execute("write /docs/api/auth.md '# Auth API\nPOST /auth/login'")

# An agent explores just like a developer would
cli.execute("tree /docs")              # See the structure
cli.execute("grep -rn 'POST' /docs")   # Search for patterns
cli.execute("cat /docs/api/users.md")  # Read a file
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
    description="Execute filesystem commands: ls, cat, grep, find, tree, head, tail, wc",
    func=cli.execute,
)
```

## AgentCLI Configuration

```python
AgentCLI(
    vfs=None,
    structured=False,
    readonly=False,
    allowed_commands=None,
    disabled_commands=None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vfs` | `VirtualFileSystem \| None` | `None` | Existing VFS to use; creates a new empty one if omitted |
| `structured` | `bool \| set[str]` | `False` | LLM-optimized output (see below) |
| `readonly` | `bool` | `False` | Disable all write commands (`write`, `append`, `rm`, `cp`, `mv`, `mkdir`, `touch`) |
| `allowed_commands` | `set[str] \| None` | `None` | Whitelist of permitted commands; mutually exclusive with `disabled_commands` |
| `disabled_commands` | `set[str] \| None` | `None` | Blacklist of forbidden commands; mutually exclusive with `allowed_commands` |

### `structured` mode

Controls token-efficient output formatting for LLM consumption:

- `False` — raw Unix-style output (default)
- `True` — apply LLM formatting to all supported commands: `ls`, `tree`, `grep`, `find`, `wc`
- `set[str]` — apply formatting only to the specified commands, e.g. `structured={"grep", "tree"}`

```python
cli = AgentCLI(structured=True)
```

```
# grep (standard)                    # grep (structured)
/docs/api/auth.md:3:POST /api/auth   [/docs/api/auth.md]
/docs/api/users.md:3:POST /api/users   L3: POST /api/auth
                                     [/docs/api/users.md]
                                       L3: POST /api/users
```

### Command access control

```python
# Only allow read commands
cli = AgentCLI(allowed_commands={"ls", "cat", "grep", "find", "tree", "head", "tail", "wc", "pwd"})

# Or just disable specific ones
cli = AgentCLI(disabled_commands={"rm", "mv"})

# Shorthand for disabling all writes
cli = AgentCLI(readonly=True)
```

## Commands

Pipes (`|`) and output redirection (`>`, `>>`) are supported between commands.

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `ls` | List directory | `-l` `-h` `-R` `-S` `-a` `-d` `-1` `-r` `-F` |
| `tree` | Directory tree | `-L` `-d` `-a` |
| `cat` | Display files | `-n` `-b` `-s` |
| `head` / `tail` | First/last lines | `-n` `-c` |
| `grep` | Search contents | `-r` `-i` `-n` `-l` `-c` `-v` `-w` `-x` `-F` `-o` `-A`/`-B`/`-C` `--include` `--exclude` `--max-depth` |
| `find` | Find files/dirs | `-name` `-iname` `-type` `-path` `-size` `-empty` `-maxdepth` `-mindepth` `-delete` |
| `sed` | Stream editor | `-n` `-e`; supports `p`, `d`, `q`, `=` commands |
| `wc` | Count lines/words/bytes | `-l` `-w` `-c` `-m` |
| `mkdir` | Create directory | `-p` `-v` |
| `touch` | Create empty file | `-c` |
| `write` | Write content to file | `write <path> <content>` |
| `append` | Append content to file | `append <path> <content>` |
| `cp` | Copy | `-r` `-a` `-n` `-v` |
| `mv` | Move/rename | `-f` `-n` `-v` |
| `rm` | Remove | `-r` `-f` `-v` |
| `pwd` / `cd` | Navigate | `cd -` `cd ~` |

Use `cli.help()` for full help text, or `cli.help("grep")` for a specific command.

## Python API

Direct access to the underlying VFS:

```python
from agent_clifs import VirtualFileSystem

vfs = VirtualFileSystem()
vfs.load_from_dict({"/file.txt": "hello"})  # bulk load
content = vfs.read_file("/file.txt")         # read
vfs.write_file("/new.txt", "world")          # write
vfs.mkdir("/data", parents=True)             # create directory
snapshot = vfs.to_dict()                     # export as {path: content}
```

## License

[Unlicense](./LICENSE) — public domain.

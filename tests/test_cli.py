from __future__ import annotations

import pytest
from agent_clifs import AgentCLI, VirtualFileSystem
from agent_clifs.exceptions import CommandError


class TestExecute:
    def test_basic_command(self, cli):
        result = cli.execute("pwd")
        assert result == "/"

    def test_unknown_command_raises_with_suggestions(self, cli):
        with pytest.raises(CommandError, match="unknown command"):
            cli.execute("badcmd")

    def test_empty_string_returns_empty(self, cli):
        result = cli.execute("")
        assert result == ""

    def test_unclosed_quotes_raises(self, cli):
        with pytest.raises(CommandError, match="syntax error"):
            cli.execute("cat 'unclosed")

    def test_command_with_args(self, cli):
        result = cli.execute("cat /src/utils.py")
        assert "helper" in result


class TestHelp:
    def test_help_all_commands(self, cli):
        result = cli.help()
        assert "Available commands:" in result
        assert "grep" in result
        assert "find" in result

    def test_help_specific_command(self, cli):
        result = cli.help("grep")
        assert result

    def test_help_unknown_raises(self, cli):
        with pytest.raises(CommandError, match="unknown command"):
            cli.help("nonexistent")

    def test_help_via_execute(self, cli):
        result = cli.execute("help")
        assert "Available commands:" in result

    def test_help_command_via_execute(self, cli):
        result = cli.execute("help cat")
        assert result


class TestAvailableCommands:
    def test_returns_sorted_list(self, cli):
        cmds = cli.available_commands()
        assert cmds == sorted(cmds)
        assert "grep" in cmds
        assert "find" in cmds
        assert "cat" in cmds


class TestInit:
    def test_creates_own_vfs(self):
        cli = AgentCLI()
        assert isinstance(cli.vfs, VirtualFileSystem)

    def test_uses_provided_vfs(self):
        vfs = VirtualFileSystem()
        vfs.write_file("/marker.txt", "exists")
        cli = AgentCLI(vfs)
        assert cli.execute("cat /marker.txt") == "exists"


class TestFullWorkflow:
    def test_mkdir_write_cat_grep_find(self):
        cli = AgentCLI()
        cli.execute("mkdir -p /project/src")
        cli.execute("write /project/src/app.py 'def hello(): pass'")
        cli.execute("write /project/src/util.py 'def world(): pass'")

        result = cli.execute("cat /project/src/app.py")
        assert "hello" in result

        result = cli.execute("grep -r def /project")
        assert "hello" in result
        assert "world" in result

        result = cli.execute("find /project -name '*.py'")
        assert "/project/src/app.py" in result
        assert "/project/src/util.py" in result

    def test_touch_append_head_tail(self):
        cli = AgentCLI()
        cli.execute("touch /log.txt")
        for i in range(20):
            cli.execute(f"append /log.txt 'line {i}\n'")

        head_result = cli.execute("head -n 3 /log.txt")
        assert "line 0" in head_result

        tail_result = cli.execute("tail -n 3 /log.txt")
        assert "line 19" in tail_result


class TestStructuredMode:
    def test_structured_ls(self):
        cli = AgentCLI(structured=True)
        cli.execute("mkdir /mydir")
        cli.execute("write /myfile.txt hello")
        result = cli.execute("ls /")
        assert "[dir]" in result
        assert "[file]" in result

    def test_structured_grep(self):
        cli = AgentCLI(structured=True)
        cli.execute("mkdir -p /proj/src")
        cli.execute("write /proj/src/a.py 'def foo(): pass'")
        cli.execute("write /proj/src/b.py 'def bar(): pass'")
        result = cli.execute("grep -rn def /proj")
        assert "[/proj/src/a.py]" in result
        assert "[/proj/src/b.py]" in result
        assert "L1:" in result

    def test_structured_tree(self):
        cli = AgentCLI(structured=True)
        cli.execute("mkdir -p /proj/src")
        cli.execute("write /proj/src/app.py hello")
        result = cli.execute("tree /proj")
        assert "\u2500" not in result
        assert "\u2502" not in result
        assert "\u251c" not in result
        assert "\u2514" not in result

    def test_structured_find(self):
        cli = AgentCLI(structured=True)
        cli.execute("mkdir /d")
        cli.execute("write /f.txt hello")
        result = cli.execute("find / -maxdepth 1")
        assert "[dir]" in result
        assert "[file]" in result

    def test_structured_wc(self):
        cli = AgentCLI(structured=True)
        cli.execute("write /f.txt 'hello world\n'")
        result = cli.execute("wc /f.txt")
        assert "lines" in result
        assert "words" in result
        assert "bytes" in result

    def test_structured_cat_passthrough(self):
        cli = AgentCLI(structured=True)
        cli.execute("write /f.txt hello")
        structured = cli.execute("cat /f.txt")
        assert structured == "hello"

    def test_structured_init(self):
        cli = AgentCLI(structured=True)
        assert cli.structured is True
        assert cli._formatter is not None

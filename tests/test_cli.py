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


class TestReadonlyMode:
    def test_readonly_blocks_write_commands(self):
        cli = AgentCLI(readonly=True)
        write_cmds = ["mkdir /d", "touch /f", "write /f hello", "append /f x", "rm /f", "cp /a /b", "mv /a /b"]
        for cmd in write_cmds:
            name = cmd.split()[0]
            with pytest.raises(CommandError, match=f"command disabled: {name} \\(readonly mode\\)"):
                cli.execute(cmd)

    def test_readonly_allows_read_commands(self):
        cli = AgentCLI(readonly=True)
        assert cli.execute("pwd") == "/"
        assert isinstance(cli.execute("ls /"), str)

    def test_readonly_available_commands_excludes_writes(self):
        cli = AgentCLI(readonly=True)
        cmds = cli.available_commands()
        for wc in ("mkdir", "touch", "write", "append", "rm", "cp", "mv"):
            assert wc not in cmds
        assert "pwd" in cmds
        assert "cat" in cmds

    def test_readonly_help_excludes_write_commands(self):
        cli = AgentCLI(readonly=True)
        result = cli.help()
        assert "File Operations" not in result
        assert "Navigation" in result
        for wc in ("mkdir", "touch", "write", "append", "rm", "cp", "mv"):
            assert wc not in result


class TestAllowedCommands:
    def test_only_allowed_commands_work(self):
        cli = AgentCLI(allowed_commands={"pwd", "ls"})
        assert cli.execute("pwd") == "/"
        assert isinstance(cli.execute("ls /"), str)

    def test_disallowed_commands_raise(self):
        cli = AgentCLI(allowed_commands={"pwd", "ls"})
        with pytest.raises(CommandError, match="command disabled: cat"):
            cli.execute("cat /nonexist")

    def test_available_commands_reflects_allowed(self):
        cli = AgentCLI(allowed_commands={"pwd", "ls", "cat"})
        assert cli.available_commands() == ["cat", "ls", "pwd"]


class TestDisabledCommands:
    def test_disabled_commands_blocked(self):
        cli = AgentCLI(disabled_commands={"rm", "mv"})
        with pytest.raises(CommandError, match="command disabled: rm"):
            cli.execute("rm /x")
        with pytest.raises(CommandError, match="command disabled: mv"):
            cli.execute("mv /a /b")

    def test_non_disabled_commands_work(self):
        cli = AgentCLI(disabled_commands={"rm"})
        assert cli.execute("pwd") == "/"

    def test_available_commands_excludes_disabled(self):
        cli = AgentCLI(disabled_commands={"rm", "mv"})
        cmds = cli.available_commands()
        assert "rm" not in cmds
        assert "mv" not in cmds
        assert "pwd" in cmds


class TestCommandToggleValidation:
    def test_both_allowed_and_disabled_raises_value_error(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            AgentCLI(allowed_commands={"pwd"}, disabled_commands={"rm"})

    def test_unknown_allowed_command_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown command.*in allowed_commands"):
            AgentCLI(allowed_commands={"pwd", "bogus"})

    def test_unknown_disabled_command_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown command.*in disabled_commands"):
            AgentCLI(disabled_commands={"bogus"})

    def test_readonly_overrides_allowed_commands(self):
        cli = AgentCLI(readonly=True, allowed_commands={"pwd", "write", "cat"})
        assert cli.execute("pwd") == "/"
        with pytest.raises(CommandError, match="readonly mode"):
            cli.execute("write /f hello")
        assert "write" not in cli.available_commands()
        assert "cat" in cli.available_commands()


class TestCommandToggleSecurity:
    def test_disabled_command_not_in_active_dict(self):
        cli = AgentCLI(disabled_commands={"rm"})
        assert "rm" not in cli._active_commands

    def test_help_for_disabled_command_raises(self):
        cli = AgentCLI(disabled_commands={"rm"})
        with pytest.raises(CommandError, match="command disabled"):
            cli.help("rm")

    def test_help_via_execute_for_disabled_command_raises(self):
        cli = AgentCLI(disabled_commands={"rm"})
        with pytest.raises(CommandError, match="command disabled"):
            cli.execute("help rm")


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


class TestPerCommandStructured:
    """structured= accepts a set to enable formatting only for named commands."""

    def test_set_formats_only_listed_commands(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured={"tree"})
        tree_out = cli.execute("tree /src")
        ls_out = cli.execute("ls /src")
        # tree should be formatted (full paths, no box chars)
        assert "[file] /src/main.py" in tree_out
        assert "├" not in tree_out
        # ls should NOT be formatted (no [file]/[dir] prefix)
        assert "[file]" not in ls_out
        assert "[dir]" not in ls_out

    def test_true_formats_all_commands(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured=True)
        ls_out = cli.execute("ls /src")
        assert "[file]" in ls_out or "[dir]" in ls_out

    def test_false_formats_nothing(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured=False)
        ls_out = cli.execute("ls /src")
        assert "[file]" not in ls_out
        assert "[dir]" not in ls_out

    def test_empty_set_formats_nothing(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured=set())
        tree_out = cli.execute("tree /src")
        assert "[file]" not in tree_out

    def test_frozenset_accepted(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured=frozenset({"grep"}))
        result = cli.execute("grep -rn def /src")
        assert "[/src" in result  # LLM grep format groups by file

    def test_set_find_only(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured={"find"})
        find_out = cli.execute("find /src -type f")
        ls_out = cli.execute("ls /src")
        # find should be formatted
        assert "[file]" in find_out
        # ls should NOT be formatted
        assert "[file]" not in ls_out
        assert "[dir]" not in ls_out

    def test_set_wc_only(self, populated_vfs):
        cli = AgentCLI(populated_vfs, structured={"wc"})
        wc_out = cli.execute("wc /src/main.py")
        tree_out = cli.execute("tree /src")
        # wc should be formatted (labeled)
        assert "lines" in wc_out
        assert "words" in wc_out
        # tree should NOT be formatted (still has box chars)
        assert "├" in tree_out or "└" in tree_out

    def test_structured_attribute_stored(self, populated_vfs):
        s = {"tree", "grep"}
        cli = AgentCLI(populated_vfs, structured=s)
        assert cli.structured == s

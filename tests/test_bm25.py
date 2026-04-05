"""Tests for the BM25 ranking module and its integration with grep."""

from __future__ import annotations

import pytest

from agent_clifs import AgentCLI, VirtualFileSystem
from agent_clifs.bm25 import BM25Index, extract_query_tokens, tokenize


class TestTokenize:
    def test_basic(self):
        assert tokenize("hello world") == ["hello", "world"]

    def test_lowercase(self):
        assert tokenize("Hello World") == ["hello", "world"]

    def test_filters_single_chars(self):
        assert "a" not in tokenize("a cat")
        assert "cat" in tokenize("a cat")

    def test_alphanumeric_and_underscore(self):
        tokens = tokenize("snake_case camelCase abc123")
        assert "snake_case" in tokens
        assert "camelcase" in tokens
        assert "abc123" in tokens

    def test_strips_punctuation(self):
        tokens = tokenize("hello, world! foo.bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens
        assert "bar" in tokens

    def test_empty_string(self):
        assert tokenize("") == []


class TestExtractQueryTokens:
    def test_fixed_string_simple(self):
        tokens = extract_query_tokens("hello world", fixed_string=True)
        assert tokens == ["hello", "world"]

    def test_fixed_string_preserves_literals(self):
        tokens = extract_query_tokens("def my_function", fixed_string=True)
        assert "def" in tokens
        assert "my_function" in tokens

    def test_regex_strips_metacharacters(self):
        tokens = extract_query_tokens(r"def\s+\w+", fixed_string=False)
        assert "def" in tokens
        assert tokens == ["def"]  # \s and \w stripped

    def test_regex_keeps_literal_words(self):
        tokens = extract_query_tokens(r"class\s+MyClass", fixed_string=False)
        assert "class" in tokens
        assert "myclass" in tokens

    def test_regex_anchors_stripped(self):
        tokens = extract_query_tokens(r"^import\s+os$", fixed_string=False)
        assert "import" in tokens
        assert "os" in tokens

    def test_regex_empty_after_strip(self):
        # Pattern with only metacharacters yields no tokens
        assert extract_query_tokens(r".*+?[]", fixed_string=False) == []

    def test_default_is_regex_mode(self):
        tokens = extract_query_tokens("hello")
        assert tokens == ["hello"]


class TestBM25Index:
    @pytest.fixture
    def small_corpus(self):
        return {
            "/a.txt": "python python python code",
            "/b.txt": "java code enterprise beans",
            "/c.txt": "python code snippet example",
        }

    def test_build_sets_document_count(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        assert idx._n == 3

    def test_rank_most_relevant_first(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        ranked = idx.rank(["python"], list(small_corpus))
        # /a.txt has "python" 3×, /c.txt has it 1×, /b.txt has none
        assert ranked[0] == "/a.txt"
        assert ranked[-1] == "/b.txt"

    def test_rank_empty_tokens_returns_original_order(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        files = ["/a.txt", "/b.txt", "/c.txt"]
        assert idx.rank([], files) == files

    def test_top_files_limits_count(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        result = idx.top_files(["python"], list(small_corpus), 2)
        assert len(result) == 2

    def test_top_files_returns_most_relevant(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        result = idx.top_files(["python"], list(small_corpus), 2)
        assert "/a.txt" in result
        assert "/c.txt" in result
        assert "/b.txt" not in result

    def test_build_empty_corpus(self):
        idx = BM25Index()
        idx.build({})
        assert idx._n == 0
        assert idx.rank(["anything"], []) == []

    def test_score_zero_for_unknown_file(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        assert idx._score(["python"], "/nonexistent.txt") == 0.0

    def test_score_zero_when_term_absent(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        assert idx._score(["ruby"], "/a.txt") == 0.0

    def test_rebuild_with_build_again(self, small_corpus):
        idx = BM25Index()
        idx.build(small_corpus)
        idx.build({"/x.txt": "rust systems programming"})
        assert idx._n == 1
        assert idx.rank(["rust"], ["/x.txt"])[0] == "/x.txt"


class TestAgentCLIBM25Integration:
    @pytest.fixture
    def bm25_cli(self):
        vfs = VirtualFileSystem()
        vfs.load_from_dict(
            {
                "/src/auth.py": "def login(user, password):\n    authenticate(user, password)\n",
                "/src/db.py": "def connect(host, port):\n    return Connection(host, port)\n",
                "/src/utils.py": "def helper():\n    return 42\n",
                "/docs/auth.md": "# Authentication\n\nUse login() to authenticate users.\n",
                "/docs/db.md": "# Database\n\nConnect using connect(host, port).\n",
            }
        )
        return AgentCLI(vfs, bm25_top_files=2)

    def test_grep_limits_files_searched(self, bm25_cli):
        # "authenticate" is only in /src/auth.py and /docs/auth.md — both
        # should be in the BM25 top-2 for that query.
        result = bm25_cli.execute("grep -r authenticate /")
        assert "authenticate" in result

    def test_grep_without_bm25_searches_all_files(self):
        vfs = VirtualFileSystem()
        vfs.load_from_dict(
            {
                "/a.py": "def foo(): pass\n",
                "/b.py": "def bar(): pass\n",
            }
        )
        cli = AgentCLI(vfs)  # no BM25
        result = cli.execute("grep -r def /")
        assert "/a.py" in result
        assert "/b.py" in result

    def test_bm25_index_attached_to_vfs(self):
        vfs = VirtualFileSystem()
        vfs.load_from_dict({"/f.txt": "hello world"})
        cli = AgentCLI(vfs, bm25_top_files=5)
        assert vfs._bm25_index is not None
        assert vfs._bm25_top_n == 5

    def test_no_bm25_when_not_configured(self):
        vfs = VirtualFileSystem()
        vfs.load_from_dict({"/f.txt": "hello world"})
        AgentCLI(vfs)  # default, no bm25
        assert vfs._bm25_index is None

    def test_reindex_after_loading_files(self):
        cli = AgentCLI(bm25_top_files=3)
        # VFS is empty at init — index built but empty
        assert cli.vfs._bm25_index is not None
        assert cli.vfs._bm25_index._n == 0

        cli.vfs.load_from_dict({"/a.txt": "python ranking bm25"})
        cli.reindex()
        assert cli.vfs._bm25_index._n == 1

    def test_reindex_noop_without_bm25(self):
        cli = AgentCLI()
        cli.reindex()  # should not raise
        assert cli.vfs._bm25_index is None

    def test_bm25_top_files_respected(self):
        vfs = VirtualFileSystem()
        # 5 files all containing "word", but only top-2 should be searched
        vfs.load_from_dict(
            {
                "/high.txt": "word word word word word relevant content here",
                "/mid.txt": "word relevant content here",
                "/low1.txt": "word other stuff one",
                "/low2.txt": "word other stuff two",
                "/low3.txt": "word other stuff three",
            }
        )
        cli = AgentCLI(vfs, bm25_top_files=2)
        result = cli.execute("grep -rl word /")
        matched = result.strip().splitlines()
        # Only 2 files should appear (top-2 by BM25)
        assert len(matched) <= 2

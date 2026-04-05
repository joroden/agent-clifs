"""In-memory BM25 ranking index for agent-clifs."""

from __future__ import annotations

import math
import re
from collections import defaultdict


def tokenize(text: str) -> list[str]:
    """Split *text* into lowercase alphanumeric tokens of length >= 2."""
    return [w.lower() for w in re.findall(r"[a-zA-Z0-9_]+", text) if len(w) >= 2]


def extract_query_tokens(pattern: str, *, fixed_string: bool = False) -> list[str]:
    """Extract BM25 query terms from a grep pattern.

    For fixed-string patterns (``-F``), tokenize the literal text directly.
    For regex patterns, strip regex metacharacters and escape sequences first
    so only the literal word portions remain.
    """
    if fixed_string:
        return tokenize(pattern)
    # Replace regex escape sequences (\s, \w, \d, \b, …) with a space so that
    # the surrounding literal text is still tokenized correctly.
    cleaned = re.sub(r"\\[a-zA-Z0-9]", " ", pattern)
    # Remove remaining non-alphanumeric/underscore characters (metacharacters).
    cleaned = re.sub(r"[^a-zA-Z0-9_\s]", " ", cleaned)
    return tokenize(cleaned)


class BM25Index:
    """BM25 ranking index over a set of in-memory text documents.

    Build the index once with :meth:`build`, then call :meth:`top_files`
    to rank a list of candidate file paths by relevance to a set of query tokens.

    BM25 parameters follow common defaults: ``k1=1.5``, ``b=0.75``.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._tf: dict[str, dict[str, int]] = {}  # path → {term: count}
        self._dl: dict[str, int] = {}  # path → document length (token count)
        self._df: dict[str, int] = {}  # term → number of docs containing it
        self._n: int = 0  # total number of documents
        self._avgdl: float = 0.0  # average document length

    def build(self, files: dict[str, str]) -> None:
        """Build the index from a ``{path: content}`` mapping."""
        self._tf = {}
        self._dl = {}
        df: dict[str, int] = defaultdict(int)

        for path, content in files.items():
            terms = tokenize(content)
            tf: dict[str, int] = defaultdict(int)
            for term in terms:
                tf[term] += 1
            self._tf[path] = dict(tf)
            self._dl[path] = len(terms)
            for term in tf:
                df[term] += 1

        self._df = dict(df)
        self._n = len(files)
        self._avgdl = sum(self._dl.values()) / self._n if self._n > 0 else 0.0

    def _score(self, query_tokens: list[str], path: str) -> float:
        tf_map = self._tf.get(path, {})
        dl = self._dl.get(path, 0)
        if not tf_map:
            return 0.0

        dl_factor = (
            self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            if self._avgdl > 0
            else self.k1
        )
        score = 0.0
        for term in query_tokens:
            tf = tf_map.get(term, 0)
            df = self._df.get(term, 0)
            if tf == 0 or df == 0:
                continue
            idf = math.log((self._n - df + 0.5) / (df + 0.5) + 1.0)
            tf_norm = tf * (self.k1 + 1) / (tf + dl_factor)
            score += idf * tf_norm
        return score

    def rank(self, query_tokens: list[str], candidate_files: list[str]) -> list[str]:
        """Return *candidate_files* sorted by BM25 score descending.

        Files scoring zero are placed at the end in their original relative order.
        """
        if not query_tokens:
            return list(candidate_files)
        scored = [(f, self._score(query_tokens, f)) for f in candidate_files]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [f for f, _ in scored]

    def top_files(
        self, query_tokens: list[str], candidate_files: list[str], n: int
    ) -> list[str]:
        """Return the top *n* files from *candidate_files* by BM25 score."""
        return self.rank(query_tokens, candidate_files)[:n]

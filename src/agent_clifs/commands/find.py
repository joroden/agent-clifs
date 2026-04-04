"""find command for the virtual filesystem."""

from __future__ import annotations

import fnmatch
import re
from typing import TYPE_CHECKING

from agent_clifs.exceptions import CommandError

if TYPE_CHECKING:
    from agent_clifs.vfs import VirtualFileSystem


# ------------------------------------------------------------------
# find – expression-parser helpers
# ------------------------------------------------------------------

# Tokens that signal the start of a find expression (vs. a starting path).
_FIND_EXPR_TOKENS: frozenset[str] = frozenset({
    "-name", "-iname", "-type", "-path", "-maxdepth", "-mindepth",
    "-size", "-empty", "-newer", "-print", "-delete", "-exec",
    "-not", "-a", "-and", "-o", "-or", "!", "(", ")"
})


def _make_size_pred(spec: str, vfs: "VirtualFileSystem"):  # type: ignore[return]
    """Return a predicate function for ``-size SPEC`` (e.g. ``+5k``, ``-10M``)."""
    m = re.match(r"^([+-]?)(\d+)([cwbkMG]?)$", spec)
    if not m:
        raise CommandError(f"find: -size: invalid size spec '{spec}'")
    cmp_op, num_s, unit = m.groups()
    num = int(num_s)
    unit_bytes: dict[str, int] = {
        "": 512, "b": 512, "c": 1, "w": 2,
        "k": 1024, "M": 1024 * 1024, "G": 1024 * 1024 * 1024,
    }
    factor = unit_bytes[unit]

    def _pred(abs_p: str, t: str, dp: str, bn: str) -> bool:
        if t != "f":
            return False
        try:
            size = len(vfs.read_file(abs_p).encode())
        except Exception:
            return False
        # Convert bytes to blocks; ceil-divide for block-based units
        n = -(-size // factor) if factor > 1 else size  # ceil div
        if cmp_op == "+":
            return n > num
        if cmp_op == "-":
            return n < num
        return n == num

    return _pred


def _safe_read(vfs: "VirtualFileSystem", path: str) -> str:
    try:
        return vfs.read_file(path)
    except Exception:
        return ""


class _FindParser:
    """Recursive-descent parser for ``find`` predicate expressions.

    Grammar::

        expr    = or
        or      = and ( ('-o' | '-or') and )*
        and     = not  ( ('-a' | '-and' | <implicit>) not )*
        not     = ('!' | '-not') not | primary
        primary = '(' expr ')' | predicate | action
    """

    def __init__(self, vfs: "VirtualFileSystem", tokens: list[str]) -> None:
        self.vfs = vfs
        self.tokens: list[str] = list(tokens)
        self.pos = 0
        self.maxdepth: int | None = None
        self.mindepth: int | None = None
        self.has_delete = False
        self._hoist_depth_options()

    # ------------------------------------------------------------------
    # Pre-processing
    # ------------------------------------------------------------------

    def _hoist_depth_options(self) -> None:
        """-maxdepth / -mindepth are global options; pull them out early."""
        remaining: list[str] = []
        i = 0
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok in ("-maxdepth", "-mindepth") and i + 1 < len(self.tokens):
                try:
                    val = int(self.tokens[i + 1])
                except ValueError:
                    raise CommandError(
                        f"find: {tok}: invalid number '{self.tokens[i + 1]}'"
                    )
                if tok == "-maxdepth":
                    self.maxdepth = val
                else:
                    self.mindepth = val
                i += 2
            else:
                remaining.append(self.tokens[i])
                i += 1
        self.tokens = remaining

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    @property
    def _cur(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _need(self, flag: str) -> str:
        if self.pos >= len(self.tokens):
            raise CommandError(f"find: missing argument to '{flag}'")
        return self._advance()

    # ------------------------------------------------------------------
    # Grammar rules
    # ------------------------------------------------------------------

    def parse(self):
        if self.pos >= len(self.tokens):
            return lambda *_: True  # empty expression → match everything
        pred = self._or()
        if self.pos < len(self.tokens):
            raise CommandError(f"find: unexpected token '{self.tokens[self.pos]}'")
        return pred

    def _or(self):
        left = self._and()
        while self._cur in ("-o", "-or"):
            self._advance()
            right = self._and()
            left = self._mk_or(left, right)
        return left

    def _and(self):
        left = self._not()
        while self._cur not in (None, "-o", "-or", ")"):
            if self._cur in ("-a", "-and"):
                self._advance()
            right = self._not()
            left = self._mk_and(left, right)
        return left

    def _not(self):
        if self._cur in ("!", "-not"):
            self._advance()
            return self._mk_not(self._not())
        return self._primary()

    def _primary(self):  # noqa: C901
        tok = self._cur
        if tok is None:
            return lambda *_: True

        if tok == "(":
            self._advance()
            inner = self._or()
            if self._cur == ")":
                self._advance()
            else:
                raise CommandError("find: unmatched '('")
            return inner

        self._advance()  # consume the predicate token

        if tok == "-name":
            pat = self._need("-name")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(bn, p)

        if tok == "-iname":
            pat = self._need("-iname")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(bn.lower(), p.lower())

        if tok == "-type":
            tv = self._need("-type")
            if tv not in ("f", "d"):
                raise CommandError(f"find: -type: unknown type '{tv}'; use 'f' or 'd'")
            return lambda a, t, d, bn, v=tv: t == v

        if tok == "-path":
            pat = self._need("-path")
            return lambda a, t, d, bn, p=pat: fnmatch.fnmatch(d, p)

        if tok == "-size":
            return _make_size_pred(self._need("-size"), self.vfs)

        if tok == "-empty":
            vfs = self.vfs
            return lambda a, t, d, bn: (
                (t == "f" and _safe_read(vfs, a) == "")
                or (t == "d" and len(vfs.list_dir(a)) == 0)
            )

        if tok == "-newer":
            self._need("-newer")  # consume the ref-path argument
            raise CommandError("find: -newer: not supported (VFS has no timestamps)")

        if tok == "-exec":
            raise CommandError(
                "find: -exec is not supported in VFS context; "
                "pipe find output to other commands instead"
            )

        if tok == "-print":
            return lambda *_: True  # default action; always true

        if tok == "-delete":
            self.has_delete = True
            return lambda *_: True  # deletion is handled after the walk

        raise CommandError(f"find: unknown predicate '{tok}'")

    # ------------------------------------------------------------------
    # Combinator helpers (capture by default arg to avoid late-binding)
    # ------------------------------------------------------------------

    @staticmethod
    def _mk_or(l, r):
        return lambda a, t, d, bn, lp=l, rp=r: lp(a, t, d, bn) or rp(a, t, d, bn)

    @staticmethod
    def _mk_and(l, r):
        return lambda a, t, d, bn, lp=l, rp=r: lp(a, t, d, bn) and rp(a, t, d, bn)

    @staticmethod
    def _mk_not(inner):
        return lambda a, t, d, bn, i=inner: not i(a, t, d, bn)


# ------------------------------------------------------------------
# find
# ------------------------------------------------------------------

def cmd_find(vfs: VirtualFileSystem, args: list[str]) -> str:
    """Find files and directories matching given criteria."""
    # Split leading positional arguments (starting paths) from the expression.
    paths: list[str] = []
    i = 0
    while i < len(args) and args[i] not in _FIND_EXPR_TOKENS:
        paths.append(args[i])
        i += 1
    if not paths:
        paths = ["."]

    fp = _FindParser(vfs, args[i:])
    predicate = fp.parse()

    results: list[str] = []
    to_delete: list[str] = []

    for start in paths:
        abs_start = vfs.resolve_path(start)
        if not vfs.is_dir(abs_start):
            if vfs.exists(abs_start):
                raise CommandError(f"find: '{start}': Not a directory")
            raise CommandError(f"find: '{start}': No such file or directory")

        use_rel = not start.startswith("/")

        def _disp(p: str, _a=abs_start, _s=start, _r=use_rel) -> str:
            if p == _a:
                return _s if _r else p
            suffix = p[len(_a):] if _a != "/" else p
            return (_s.rstrip("/") + suffix) if _r else p

        def _depth(p: str, _a=abs_start) -> int:
            if p == _a:
                return 0
            seg = p[len(_a):] if _a != "/" else p
            return seg.count("/")

        for dirpath, _dirnames, filenames in vfs.walk(abs_start):
            ddepth = _depth(dirpath)

            if fp.maxdepth is not None and ddepth > fp.maxdepth:
                continue

            # Evaluate this directory entry
            if fp.mindepth is None or ddepth >= fp.mindepth:
                dp = _disp(dirpath)
                bn = dirpath.rsplit("/", 1)[-1] if dirpath != "/" else "/"
                if predicate(dirpath, "d", dp, bn):
                    results.append(dp)
                    if fp.has_delete:
                        to_delete.append(dirpath)

            # Evaluate files inside this directory
            if fp.maxdepth is None or ddepth + 1 <= fp.maxdepth:
                for fname in filenames:
                    fpath = dirpath.rstrip("/") + "/" + fname
                    fdepth = ddepth + 1
                    if fp.mindepth is None or fdepth >= fp.mindepth:
                        fdp = _disp(fpath)
                        if predicate(fpath, "f", fdp, fname):
                            results.append(fdp)
                            if fp.has_delete:
                                to_delete.append(fpath)

    if fp.has_delete:
        # Delete files first, then directories deepest-first to avoid conflicts
        for p in [p for p in to_delete if vfs.is_file(p)]:
            try:
                vfs.remove_file(p)
            except Exception:
                pass
        for p in sorted((p for p in to_delete if vfs.is_dir(p)), reverse=True):
            try:
                vfs.rmdir(p, recursive=True)
            except Exception:
                pass
        return ""

    return "\n".join(sorted(results))

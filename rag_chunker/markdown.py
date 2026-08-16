"""Structure-aware markdown parsing.

The parser is deliberately shallow: it recognises the constructs whose integrity
matters to a retrieval chunker -- ATX headings, fenced code, pipe tables, list
runs and paragraphs -- and treats everything else as prose. Inline syntax is
left completely alone, because a chunker never needs to understand it.
"""

import re

from .tokens import estimate_tokens

__all__ = ["Block", "parse_blocks", "BLOCK_KINDS"]

BLOCK_KINDS = ("heading", "paragraph", "list", "code", "table")

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*\S)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_BULLET = re.compile(r"^[ \t]*([-*+]|[0-9]+[.)])[ \t]+")
_TABLE_SEPARATOR = re.compile(r"^[ \t]*\|?[ \t:|-]*-[ \t:|-]*\|?[ \t]*$")


class Block(object):
    """A contiguous run of lines that the chunker treats as one unit."""

    __slots__ = ("kind", "text", "start_line", "end_line", "level", "title", "tokens")

    def __init__(self, kind, text, start_line, end_line, level=0, title=None):
        if kind not in BLOCK_KINDS:
            raise ValueError("unknown block kind: %r" % (kind,))
        self.kind = kind
        self.text = text
        self.start_line = start_line
        self.end_line = end_line
        self.level = level
        self.title = title
        self.tokens = estimate_tokens(text)

    @property
    def is_atomic(self):
        """Code and tables are never split; cutting them destroys their meaning."""
        return self.kind in ("code", "table")

    def __repr__(self):
        return "Block(kind=%s, lines=%d-%d, tokens=%d)" % (
            self.kind,
            self.start_line,
            self.end_line,
            self.tokens,
        )


def _is_table_start(lines, index):
    if "|" not in lines[index]:
        return False
    if index + 1 >= len(lines):
        return False
    following = lines[index + 1]
    return "|" in following and _TABLE_SEPARATOR.match(following) is not None


def parse_blocks(text):
    """Parse ``text`` into a list of :class:`Block` in document order."""
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    blocks = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        fence = _FENCE.match(line)
        if fence is not None:
            marker = fence.group(1)
            start = index
            index += 1
            while index < total:
                if lines[index].strip().startswith(marker):
                    index += 1
                    break
                index += 1
            blocks.append(
                Block(
                    "code",
                    "\n".join(lines[start:index]).rstrip(),
                    start + 1,
                    index,
                )
            )
            continue

        heading = _HEADING.match(line)
        if heading is not None:
            blocks.append(
                Block(
                    "heading",
                    line.strip(),
                    index + 1,
                    index + 1,
                    level=len(heading.group(1)),
                    title=heading.group(2).strip(),
                )
            )
            index += 1
            continue

        if _is_table_start(lines, index):
            start = index
            while index < total and lines[index].strip() and "|" in lines[index]:
                index += 1
            blocks.append(
                Block("table", "\n".join(lines[start:index]).rstrip(), start + 1, index)
            )
            continue

        start = index
        kind = "list" if _BULLET.match(line) else "paragraph"
        while index < total:
            current = lines[index]
            if not current.strip():
                break
            if index > start and (
                _HEADING.match(current)
                or _FENCE.match(current)
                or _is_table_start(lines, index)
            ):
                break
            index += 1
        blocks.append(
            Block(kind, "\n".join(lines[start:index]).rstrip(), start + 1, index)
        )

    return blocks

"""Heuristic token estimation with no third-party dependencies.

Chunk sizes for a retrieval pipeline are budget decisions, not billing figures,
so this module trades exactness for zero install weight. It walks the text once
and scores each run of characters:

* ASCII words       ~ 4 characters per token (minimum one token per word)
* digit runs        ~ 3 characters per token (minimum one token per run)
* CJK characters    ~ 1 token per character
* newlines          ~ 0.5 tokens each (runs of newlines merge)
* other symbols     ~ 0.6 tokens each
* spaces/tabs       free (they attach to the following token)

On English prose the result lands within roughly 10% of what a BPE tokenizer
reports. Every ``token_estimate`` this package emits comes from here, so a chunk
sized at 512 here may measure 470-560 with your provider's tokenizer -- leave
headroom rather than sizing chunks to the exact limit of an embedding model.
"""

import math
import re

__all__ = ["estimate_tokens", "fits_budget", "CHARS_PER_WORD_TOKEN"]

CHARS_PER_WORD_TOKEN = 4.0
CHARS_PER_NUMBER_TOKEN = 3.0
TOKENS_PER_CJK_CHAR = 1.0
TOKENS_PER_NEWLINE = 0.5
TOKENS_PER_SYMBOL = 0.6

_SCANNER = re.compile(
    r"(?P<newline>\n+)"
    r"|(?P<space>[ \t\r\f\v]+)"
    r"|(?P<word>[A-Za-z]+(?:['’][A-Za-z]+)*)"
    r"|(?P<number>[0-9]+)"
    r"|(?P<cjk>[぀-ヿ㐀-䶿一-鿿가-힯]+)"
    r"|(?P<other>.)",
    re.DOTALL,
)


def estimate_tokens(text):
    """Return an estimated token count for ``text`` as a non-negative integer."""
    if not text:
        return 0
    total = 0.0
    for match in _SCANNER.finditer(text):
        kind = match.lastgroup
        length = match.end() - match.start()
        if kind == "word":
            total += max(1.0, length / CHARS_PER_WORD_TOKEN)
        elif kind == "number":
            total += max(1.0, length / CHARS_PER_NUMBER_TOKEN)
        elif kind == "cjk":
            total += length * TOKENS_PER_CJK_CHAR
        elif kind == "newline":
            total += length * TOKENS_PER_NEWLINE
        elif kind == "other":
            total += length * TOKENS_PER_SYMBOL
    return int(math.ceil(total))


def fits_budget(text, budget):
    """True when ``text`` is estimated to fit inside ``budget`` tokens."""
    return estimate_tokens(text) <= budget

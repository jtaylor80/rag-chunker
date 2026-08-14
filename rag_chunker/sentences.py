"""Sentence segmentation used as the fallback when a paragraph is too long.

Splitting on ``.`` alone breaks on "e.g.", "Dr. Chen", "v1.2.3" and numbered
lists, and every one of those produces a chunk fragment that starts mid-thought.
The rules below are small but cover the cases that actually show up in technical
documentation.
"""

import re

__all__ = ["split_sentences", "ABBREVIATIONS"]

#: Words that end in a period without ending a sentence. Deliberately small:
#: every entry here is a sentence break the splitter will refuse to make, so a
#: word that is also common prose ("no", "min") does more harm than good.
ABBREVIATIONS = frozenset(
    """
a.m al approx cf co corp dept dr e.g eq etc fig figs i.e inc jr ltd mr mrs ms
p.m pp prof ref sr st vs vol
""".split()
)

_BOUNDARY = re.compile(r"([.!?。！？])([\"'’”)\]]*)(\s+|$)")


def _preceding_word(text, dot_index):
    end = dot_index
    start = end
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "."):
        start -= 1
    return text[start:end].lower()


def _is_false_boundary(text, dot_index):
    """True when the punctuation at ``dot_index`` does not end a sentence."""
    if text[dot_index] != ".":
        return False
    word = _preceding_word(text, dot_index)
    if not word:
        return False
    if word.isdigit():
        # "3." in a numbered list, or the "1" of "1.5"
        return True
    if len(word) == 1 and word.isalpha():
        # a middle initial such as "J."
        return True
    return word in ABBREVIATIONS or word.strip(".") in ABBREVIATIONS


def split_sentences(text):
    """Split ``text`` into sentences, keeping their terminating punctuation."""
    if not text or not text.strip():
        return []
    sentences = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        if _is_false_boundary(text, match.start(1)):
            continue
        candidate = text[start : match.end(2)].strip()
        if candidate:
            sentences.append(candidate)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences

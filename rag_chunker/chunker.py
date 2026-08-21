"""Heading-aware greedy packing of markdown blocks into token-budgeted chunks.

The document is first split into sections at heading boundaries -- a section is
a heading's path plus the body blocks that sit directly under it, before the
next heading of equal or shallower level. Each section is then packed
independently, so overlap and budget accounting never cross a heading, and a
chunk's ``heading_path`` is always unambiguous.

Within a section, blocks are added to the current chunk greedily. Code and
table blocks are atomic and are only ever emitted whole, so a chunk holding one
is flagged ``oversized`` when even a lone block blows the budget -- splitting it
would just produce two chunks neither of which makes sense on its own.
Paragraphs and lists fall back to sentence boundaries when they do not fit,
which is why ``oversized`` is otherwise rare in practice.
"""

import json

from .markdown import parse_blocks
from .sentences import split_sentences
from .tokens import estimate_tokens

__all__ = [
    "Chunk",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_OVERLAP",
    "chunk_markdown",
    "chunks_to_jsonl",
]

DEFAULT_MAX_TOKENS = 512
DEFAULT_OVERLAP = 64


class Chunk(object):
    """One packed unit of a chunked document, ready to embed."""

    __slots__ = (
        "index",
        "text",
        "body",
        "heading_path",
        "start_line",
        "end_line",
        "token_estimate",
        "oversized",
    )

    def __init__(
        self,
        text,
        body,
        heading_path,
        start_line,
        end_line,
        token_estimate,
        oversized=False,
        index=0,
    ):
        self.index = index
        self.text = text
        self.body = body
        self.heading_path = list(heading_path)
        self.start_line = start_line
        self.end_line = end_line
        self.token_estimate = token_estimate
        self.oversized = oversized

    def to_dict(self):
        """The JSONL record for this chunk."""
        return {
            "index": self.index,
            "text": self.text,
            "heading_path": list(self.heading_path),
            "start_line": self.start_line,
            "end_line": self.end_line,
            "token_estimate": self.token_estimate,
        }

    def __repr__(self):
        return "Chunk(index=%d, tokens=%d, heading_path=%r)" % (
            self.index,
            self.token_estimate,
            self.heading_path,
        )


def chunks_to_jsonl(chunks):
    """Serialise ``chunks`` as newline-delimited JSON, one object per line."""
    return "\n".join(json.dumps(chunk.to_dict(), ensure_ascii=False) for chunk in chunks)


def chunk_markdown(text, max_tokens=DEFAULT_MAX_TOKENS, overlap=DEFAULT_OVERLAP, heading_prefix=True):
    """Chunk ``text`` into a list of :class:`Chunk` in document order."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")

    chunks = []
    for heading_path, body_blocks in _split_sections(parse_blocks(text)):
        chunks.extend(_chunk_section(heading_path, body_blocks, max_tokens, overlap, heading_prefix))

    for position, chunk in enumerate(chunks):
        chunk.index = position
    return chunks


def _split_sections(blocks):
    """Group blocks into ``(heading_path, body_blocks)`` runs at heading boundaries."""
    sections = []
    heading_stack = []
    current_path = ()
    current_body = []

    for block in blocks:
        if block.kind != "heading":
            current_body.append(block)
            continue
        if current_body:
            sections.append((current_path, current_body))
            current_body = []
        while heading_stack and heading_stack[-1][0] >= block.level:
            heading_stack.pop()
        heading_stack.append((block.level, block.title))
        current_path = tuple(level_title[1] for level_title in heading_stack)

    if current_body:
        sections.append((current_path, current_body))
    return sections


def _body_text(items):
    if not items:
        return ""
    parts = [items[0]["text"]]
    for item in items[1:]:
        parts.append(item.get("sep", "\n\n"))
        parts.append(item["text"])
    return "".join(parts)


def _full_text(items, prefix):
    body = _body_text(items)
    if not prefix:
        return body
    return prefix + "\n\n" + body if body else prefix


def _make_overlap_seed(items, overlap):
    """The trailing whole sentences of ``items``, capped at ``overlap`` tokens."""
    if overlap <= 0:
        return None
    sentences = split_sentences(_body_text(items))
    if not sentences:
        return None

    picked = []
    tokens = 0
    for sentence in reversed(sentences):
        sentence_tokens = estimate_tokens(sentence)
        if tokens + sentence_tokens > overlap:
            break
        picked.append(sentence)
        tokens += sentence_tokens
    if not picked:
        return None
    picked.reverse()

    return {
        "text": " ".join(picked),
        "start_line": min(item["start_line"] for item in items),
        "end_line": max(item["end_line"] for item in items),
        "is_seed": True,
    }


def _chunk_section(heading_path, blocks, max_tokens, overlap, heading_prefix):
    prefix = " > ".join(heading_path) if heading_prefix and heading_path else ""
    chunks = []
    pending = []

    def has_real_content(items):
        return any(not item.get("is_seed") for item in items)

    def emit(items, oversized=False):
        if not has_real_content(items):
            return
        body = _body_text(items)
        chunks.append(
            Chunk(
                text=_full_text(items, prefix),
                body=body,
                heading_path=heading_path,
                start_line=min(item["start_line"] for item in items),
                end_line=max(item["end_line"] for item in items),
                token_estimate=estimate_tokens(_full_text(items, prefix)),
                oversized=oversized,
            )
        )

    def try_add(atom):
        candidate = pending + [atom]
        return candidate, estimate_tokens(_full_text(candidate, prefix)) <= max_tokens

    def flush():
        nonlocal pending
        if not has_real_content(pending):
            return
        emit(pending)
        seed = _make_overlap_seed(pending, overlap)
        pending = [seed] if seed else []

    def emit_standalone(atom):
        # Called right after flush(), so any leftover overlap seed in `pending`
        # is dropped rather than glued onto a chunk that is already oversized.
        nonlocal pending
        fits_alone = estimate_tokens(_full_text([atom], prefix)) <= max_tokens
        emit([atom], oversized=not fits_alone)
        pending = []

    for block in blocks:
        atom = {"text": block.text, "start_line": block.start_line, "end_line": block.end_line}

        candidate, fits = try_add(atom)
        if fits:
            pending = candidate
            continue

        flush()
        candidate, fits = try_add(atom)
        if fits:
            pending = candidate
            continue

        if block.is_atomic:
            emit_standalone(atom)
            continue

        # Paragraph or list too big even alone: fall back to sentence boundaries.
        for sentence in split_sentences(block.text):
            satom = {
                "text": sentence,
                "start_line": block.start_line,
                "end_line": block.end_line,
                "sep": " ",
            }
            candidate, fits = try_add(satom)
            if fits:
                pending = candidate
                continue

            flush()
            candidate, fits = try_add(satom)
            if fits:
                pending = candidate
                continue

            emit_standalone(satom)

    if pending:
        emit(pending)

    return chunks

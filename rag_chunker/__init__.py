"""Heading-aware markdown chunking for retrieval pipelines."""

from .chunker import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP,
    Chunk,
    chunk_markdown,
    chunks_to_jsonl,
)
from .markdown import Block, parse_blocks
from .sentences import split_sentences
from .tokens import estimate_tokens, fits_budget

__version__ = "0.1.0"

__all__ = [
    "Block",
    "Chunk",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_OVERLAP",
    "__version__",
    "chunk_markdown",
    "chunks_to_jsonl",
    "estimate_tokens",
    "fits_budget",
    "parse_blocks",
    "split_sentences",
]

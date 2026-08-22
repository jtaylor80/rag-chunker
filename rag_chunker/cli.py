"""Command-line entry point: ``rag-chunker`` / ``python -m rag_chunker.cli``."""

import argparse
import json
import sys

from .chunker import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP, chunk_markdown, chunks_to_jsonl

__all__ = ["main"]


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="rag-chunker",
        description="Chunk a markdown document into embeddable, heading-scoped pieces.",
    )
    parser.add_argument("path", help="markdown file to chunk, or - to read stdin")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="chunk size ceiling, heading prefix included (default: %(default)s)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_OVERLAP,
        help="trailing tokens repeated in the next chunk of a section (default: %(default)s)",
    )
    parser.add_argument(
        "--no-heading-prefix",
        action="store_true",
        help="do not prepend the heading path to the chunk text",
    )
    parser.add_argument(
        "--array",
        action="store_true",
        help="emit one indented JSON array instead of JSON lines",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="print a size summary to stderr",
    )
    parser.add_argument(
        "-o",
        dest="output",
        metavar="PATH",
        default=None,
        help="write the result to a file instead of stdout",
    )
    return parser


def _format_stats(chunks):
    if not chunks:
        return "0 chunks"
    tokens = [chunk.token_estimate for chunk in chunks]
    oversized = sum(1 for chunk in chunks if chunk.oversized)
    return "%d chunks | tokens min %d avg %d max %d | %d oversized" % (
        len(chunks),
        min(tokens),
        round(sum(tokens) / len(tokens)),
        max(tokens),
        oversized,
    )


def _render(chunks, as_array):
    if as_array:
        return json.dumps([chunk.to_dict() for chunk in chunks], indent=2, ensure_ascii=False)
    return chunks_to_jsonl(chunks)


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            print("rag-chunker: %s" % exc, file=sys.stderr)
            return 1

    try:
        chunks = chunk_markdown(
            text,
            max_tokens=args.max_tokens,
            overlap=args.overlap,
            heading_prefix=not args.no_heading_prefix,
        )
    except ValueError as exc:
        print("rag-chunker: %s" % exc, file=sys.stderr)
        return 1

    output = _render(chunks, args.array)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
            handle.write("\n")
    else:
        sys.stdout.write(output)
        sys.stdout.write("\n")

    if args.stats:
        print(_format_stats(chunks), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

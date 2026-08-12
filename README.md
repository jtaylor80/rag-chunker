# rag-chunker

Structure-aware markdown chunking for retrieval pipelines. Splits a document
into embeddable chunks that respect its shape instead of its byte offsets.

Fixed-window chunkers cut a fenced code block in half, split a table away from
its header row, and drop a paragraph into a chunk that gives no clue which
section it came from. Every one of those failures shows up later as a retrieval
miss that is hard to trace. `rag-chunker` fixes them at chunking time:

- **Chunks never span a heading**, and each chunk carries its heading path as a
  context prefix (`Runbook > Checks > Rollback`).
- **Code blocks and tables are atomic.** They are emitted whole, and flagged as
  `oversized` if that means exceeding the budget, so you can decide what to do
  rather than discovering half a function in your index.
- **Long paragraphs fall back to sentence boundaries**, with an abbreviation
  guard so `e.g.`, `Dr. Chen` and `v1.4` do not create fragments.
- **Configurable overlap** repeats trailing prose in the next chunk, and resets
  at every heading so a sentence never carries into the wrong section.
- **JSONL output** with `text`, `heading_path`, `start_line`, `end_line` and
  `token_estimate` per chunk.

Pure Python, standard library only, Python 3.9+.

## Install

```bash
pip install .
```

Or run it straight out of a checkout:

```bash
python -m rag_chunker.cli doc.md --max-tokens 512 --overlap 64
```

## Usage

```console
$ rag-chunker doc.md --max-tokens 120 --overlap 30 --stats
4 chunks | tokens min 23 avg 68 max 104 | 0 oversized
```

Standard output is one JSON object per line:

```json
{"index": 0, "text": "Vector index runbook\n\nThis runbook covers the nightly reindex job and the checks that follow it.", "heading_path": ["Vector index runbook"], "start_line": 3, "end_line": 3, "token_estimate": 23}
{"index": 2, "text": "Vector index runbook > Reindex\n\nRun the job from the scheduler, never from a laptop:\n\n```bash\npython -m pipeline.reindex \\\n  --source s3://docs/current \\\n  --max-tokens 512 \\\n  --overlap 64\n```", "heading_path": ["Vector index runbook", "Reindex"], "start_line": 17, "end_line": 24, "token_estimate": 58}
```

Note that chunk 2 holds the whole shell block. At a tighter budget the same
document splits inside the section instead, and the second chunk of a section
opens with the tail of the first:

```console
$ rag-chunker doc.md --max-tokens 60 --overlap 20 --stats
6 chunks | tokens min 23 avg 48 max 68 | 1 oversized
```

The one oversized chunk is the checks table: 68 tokens against a 60 token
budget, emitted whole because splitting a table off its header row makes both
halves useless.

Feed the output to an embedder directly:

```bash
rag-chunker doc.md --max-tokens 512 --overlap 64 | jq -r .text | your-embedder
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--max-tokens N` | `512` | Chunk size ceiling, heading prefix included |
| `--overlap N` | `64` | Trailing tokens repeated in the next chunk of a section |
| `--no-heading-prefix` | off | Do not prepend the heading path to the chunk text |
| `--array` | off | Emit one indented JSON array instead of JSON lines |
| `--stats` | off | Print a size summary to stderr |
| `-o PATH` | stdout | Write the result to a file |

Use `-` as the input path to read standard input. `--overlap` must be smaller
than `--max-tokens`.

## Library API

```python
from rag_chunker import chunk_markdown

chunks = chunk_markdown(open("doc.md").read(), max_tokens=512, overlap=64)

for chunk in chunks:
    chunk.text            # heading prefix + body, ready to embed
    chunk.body            # body without the prefix
    chunk.heading_path    # ['Vector index runbook', 'Checks']
    chunk.start_line      # 1-based, points back at the source file
    chunk.end_line
    chunk.token_estimate
    chunk.oversized       # True only for an indivisible code block or table
    chunk.to_dict()       # the JSONL record
```

Other exports are useful on their own:

| Function | Purpose |
| --- | --- |
| `parse_blocks(text)` | Markdown blocks: `heading`, `paragraph`, `list`, `code`, `table` |
| `split_sentences(text)` | Sentence splitting with the abbreviation guard |
| `estimate_tokens(text)` | The heuristic used for every `token_estimate` |
| `chunks_to_jsonl(chunks)` | Serialise a chunk list |

### What the parser recognises

ATX headings (`#` through `######`), fenced code (` ``` ` and `~~~`, including
unterminated fences), pipe tables with a separator row, bullet and ordered list
runs, and paragraphs. Inline syntax is left untouched, because a chunker never
needs to interpret it. Setext headings (underlined with `===`) are read as
ordinary paragraphs.

## About the token estimator

`token_estimate` comes from a character-class heuristic, not a real tokenizer:
about four characters per word token, one token per CJK character, and small
fixed costs for digits, newlines and symbols. On English prose it lands within
roughly 10% of a BPE count.

That accuracy is fine for chunk sizing and it keeps the package dependency-free,
but it means a chunk sized at 512 here may measure 470-560 with your provider's
tokenizer. Leave headroom rather than sizing chunks to an exact model limit.

## Test

```bash
python -m pytest tests -q
```

## License

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 jtaylor80.

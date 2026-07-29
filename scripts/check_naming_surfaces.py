#!/usr/bin/env python3
"""Reader-facing naming checker.

Guards one rule across every reader-facing surface:

    The Microsoft Foundry product name ("Model Router") must never share a
    semantic block with the synthetic single-call coverage figure (52%).

The synthetic experiment-07 arm is a *generic* single-call projection over
synthetic data. Only real product arms may be called "Model Router", and the
product must never be the thing a reader sees carrying 52% coverage.

A same-line ``grep`` is not sufficient: a table row, a card, a figure caption or
a wrapped paragraph can associate the two across several lines. This checker
therefore splits each surface into *semantic blocks* — headings, paragraphs,
list items, table rows, admonition cards, and figure alt text — and asserts that
no single block contains both.

Run standalone::

    python scripts/check_naming_surfaces.py

Exits non-zero and prints every offending block when the rule is violated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The product name, as a reader sees it. Matched after emphasis markers are
# stripped so "**Model Router**" and "내장 Model Router" both resolve.
PRODUCT_NAME = re.compile(r"Model\s+Router")

# The synthetic single-call coverage result.
SYNTHETIC_FIGURE = re.compile(r"(?<![\d.])52\s*%|(?<![\d.])0\.52(?![\d])")

# Reader-facing Markdown surfaces.
MARKDOWN_GLOBS = (
    "README.md",
    "docs/**/*.md",
    "experiments/README.md",
    "samples/workloads/README.md",
)

# Reader-facing strings embedded in the product UI.
HTML_SOURCES = ("src/router/dashboard.py",)

# Experiment metadata fields a reader sees (titles, summaries, labels).
EXPERIMENT_GLOB = "experiments/*.yaml"
EXPERIMENT_TEXT_FIELDS = ("title", "summary", "name")


@dataclass(frozen=True)
class Block:
    """One semantic unit of reader-facing text."""

    path: str
    line: int
    kind: str
    text: str


def _strip_code_fences(text: str) -> str:
    """Blank out fenced code so CLI transcripts are not read as prose.

    Line numbers are preserved so reported positions stay accurate.
    """
    out: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return "\n".join(out)


def _normalize(text: str) -> str:
    """Reduce a raw snippet to what a reader actually reads."""
    # Link and image targets carry slugs (``07-model-router.md``) that Z1
    # deliberately preserves; only the visible text is reader-facing.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<https?://[^>]*>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    # Emphasis / inline code markers.
    text = re.sub(r"[*_`]+", "", text)
    text = text.replace("&mdash;", "—").replace("&rarr;", "→")
    return re.sub(r"\s+", " ", text).strip()


def _iter_markdown_blocks(path: str, text: str) -> list[Block]:
    """Split Markdown into semantic blocks.

    Headings, table rows and figure captions are individually addressable.
    An admonition (``!!! note``) is treated as a single *card* including its
    indented body, because that is what a reader perceives as one unit.
    """
    blocks: list[Block] = []
    lines = _strip_code_fences(text).splitlines()

    buf: list[str] = []
    buf_start = 0
    buf_kind = "paragraph"

    def flush() -> None:
        nonlocal buf, buf_start, buf_kind
        if buf:
            joined = _normalize(" ".join(buf))
            if joined:
                blocks.append(Block(path, buf_start + 1, buf_kind, joined))
        buf = []
        buf_kind = "paragraph"

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())

        if not stripped:
            flush()
            i += 1
            continue

        # Admonition card: title plus every indented body line.
        if re.match(r"^(!!!|\?\?\?)\s", stripped):
            flush()
            card = [stripped]
            start = i
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    card.append("")
                    i += 1
                    continue
                if len(nxt) - len(nxt.lstrip()) > indent:
                    card.append(nxt.strip())
                    i += 1
                    continue
                break
            joined = _normalize(" ".join(card))
            if joined:
                blocks.append(Block(path, start + 1, "card", joined))
            continue

        # Heading.
        if stripped.startswith("#"):
            flush()
            blocks.append(Block(path, i + 1, "heading", _normalize(stripped)))
            i += 1
            continue

        # Table row.
        if stripped.startswith("|"):
            flush()
            blocks.append(Block(path, i + 1, "table-row", _normalize(stripped)))
            i += 1
            continue

        # List item: the marker line plus its indented continuation lines.
        if re.match(r"^([-*+]|\d+\.)\s", stripped):
            flush()
            item = [stripped]
            start = i
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    break
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= indent and re.match(r"^([-*+]|\d+\.)\s", nxt.strip()):
                    break
                if nxt_indent <= indent and nxt_indent == 0 and indent == 0:
                    # A flush-left continuation still belongs to the item.
                    item.append(nxt.strip())
                    i += 1
                    continue
                if nxt_indent > indent:
                    item.append(nxt.strip())
                    i += 1
                    continue
                break
            joined = _normalize(" ".join(item))
            if joined:
                blocks.append(Block(path, start + 1, "list-item", joined))
            continue

        if not buf:
            buf_start = i
            buf_kind = "paragraph"
        buf.append(stripped)
        i += 1

    flush()

    # Figure metadata (alt text) is reader-facing on its own.
    for idx, line in enumerate(lines):
        for alt in re.findall(r"!\[([^\]]*)\]\([^)]*\)", line):
            norm = _normalize(alt)
            if norm:
                blocks.append(Block(path, idx + 1, "figure-alt", norm))

    return blocks


_HTML_BLOCK_BOUNDARY = re.compile(
    r"</?(?:div|p|li|td|th|tr|h[1-6]|section|ul|ol|table|small|figcaption)\b[^>]*>",
    re.IGNORECASE,
)


def _iter_html_blocks(path: str, text: str) -> list[Block]:
    """Split embedded UI markup into block-level chunks.

    Reader-facing dashboard copy (card titles, chart legends, footnotes) lives
    inside Python string literals, so it is split on block-level tags rather
    than blank lines.
    """
    blocks: list[Block] = []
    offset_line = 1
    for chunk in _HTML_BLOCK_BOUNDARY.split(text):
        line_count = chunk.count("\n")
        cleaned = re.sub(r"<[^>]+>", " ", chunk)
        cleaned = _normalize(cleaned)
        if cleaned:
            blocks.append(Block(path, offset_line, "ui-block", cleaned))
        offset_line += line_count
    return blocks


def _iter_experiment_blocks(path: str, text: str) -> list[Block]:
    """Read reader-facing experiment metadata fields as individual blocks."""
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    blocks: list[Block] = []
    for field in EXPERIMENT_TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            norm = _normalize(value)
            if norm:
                blocks.append(Block(path, 1, f"metadata:{field}", norm))
    return blocks


def collect_blocks(root: Path | None = None) -> list[Block]:
    """Gather every reader-facing semantic block in the repository."""
    root = root or REPO_ROOT
    blocks: list[Block] = []

    seen: set[Path] = set()
    for pattern in MARKDOWN_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            rel = path.relative_to(root).as_posix()
            blocks.extend(_iter_markdown_blocks(rel, path.read_text(encoding="utf-8")))

    for rel in HTML_SOURCES:
        path = root / rel
        if path.is_file():
            blocks.extend(_iter_html_blocks(rel, path.read_text(encoding="utf-8")))

    for path in sorted(root.glob(EXPERIMENT_GLOB)):
        rel = path.relative_to(root).as_posix()
        blocks.extend(_iter_experiment_blocks(rel, path.read_text(encoding="utf-8")))

    return blocks


def find_violations(blocks: list[Block] | None = None) -> list[Block]:
    """Return every block that ties the product name to the synthetic figure."""
    blocks = collect_blocks() if blocks is None else blocks
    return [
        block
        for block in blocks
        if PRODUCT_NAME.search(block.text) and SYNTHETIC_FIGURE.search(block.text)
    ]


def main() -> int:
    violations = find_violations()
    if not violations:
        blocks = collect_blocks()
        print(f"naming surfaces: OK — {len(blocks)} reader-facing blocks checked")
        return 0
    print(
        f"naming surfaces: {len(violations)} block(s) tie the product name "
        "to the synthetic 52%:\n"
    )
    for block in violations:
        excerpt = block.text if len(block.text) <= 220 else block.text[:217] + "..."
        print(f"  {block.path}:{block.line} [{block.kind}]\n    {excerpt}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

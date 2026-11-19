import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import groupby

from semble.tokens import CJK_CHARACTERS
from semble.types import Chunk, ContextFragment, ExplainedSearchResult, SearchResult

_CJK_RE = re.compile(CJK_CHARACTERS)


@dataclass(frozen=True, slots=True)
class PackedContext:
    fragments: list[ContextFragment]
    packed_tokens: int
    full_file_tokens: int | None
    grep_estimated_tokens: int | None
    savings_pct: float | None


def estimate_tokens(text: str) -> int:
    """Estimate one token per 3.75 other characters and 4/3 tokens per CJK character."""
    cjk_count = len(_CJK_RE.findall(text))
    return (4 * (len(text) - cjk_count) + 20 * cjk_count + 14) // 15


def _chunk_lines(chunk: Chunk) -> dict[int, str]:
    """Map indexed line numbers to preview text, excluding the final trailing newline."""
    lines = chunk.content.split("\n", chunk.end_line - chunk.start_line + 1)
    return {line: text for line, text in zip(range(chunk.start_line, chunk.end_line + 1), lines)}


def _fragments(file_path: str, lines: dict[int, str]) -> list[ContextFragment]:
    """Join adjacent preview lines into single context fragments."""
    fragments = []
    for _, rows in groupby(enumerate(sorted(lines)), key=lambda row: row[1] - row[0]):
        numbers = [number for _, number in rows]
        content = "\n".join(lines[number] for number in numbers)
        fragments.append(ContextFragment(file_path, numbers[0], numbers[-1], content, estimate_tokens(content)))
    return fragments


def pack_chunks_to_budget(
    results: Sequence[SearchResult | ExplainedSearchResult],
    token_budget: int | None,
    *,
    file_token_count: Callable[[str], int | None] | None = None,
) -> PackedContext:
    """Pack complete ranked chunks where they fit, retaining the higher-ranked text on overlapping lines.

    Adjacent selected lines are coalesced. Full-file and grep estimates cover each
    packed file once and are unknown if any required full-file count is unavailable.
    """
    if token_budget is not None and token_budget < 0:
        raise ValueError("token_budget must be non-negative")
    if token_budget == 0:
        return PackedContext([], 0, 0, 0, 0.0)

    selected: dict[str, dict[int, str]] = {}
    by_file: dict[str, list[ContextFragment]] = {}
    costs: dict[str, int] = {}
    packed = 0
    for result in sorted(results, key=lambda row: -row.score):
        chunk = result.chunk
        path = chunk.file_path
        lines = _chunk_lines(chunk) | selected.get(path, {})
        fragments = _fragments(path, lines)
        cost = sum(fragment.estimated_tokens for fragment in fragments)
        next_total = packed + cost - costs.get(path, 0)
        if token_budget is None or next_total <= token_budget:
            selected[path] = lines
            by_file[path] = fragments
            costs[path] = cost
            packed = next_total

    counts = [file_token_count(path) if file_token_count is not None else None for path in by_file]
    full = None if None in counts else sum(count for count in counts if count is not None)
    savings = None if full is None else (100.0 * (full - packed) / full if full else 0.0)
    fragments = [fragment for file_fragments in by_file.values() for fragment in file_fragments]
    return PackedContext(fragments, packed, full, full, savings)

import pytest

from semble.context_packer import estimate_tokens, pack_chunks_to_budget
from semble.types import Chunk, SearchResult


def _hit(path: str, start: int, content: str, score: float) -> SearchResult:
    return SearchResult(Chunk(content, path, start, start + content.count("\n")), score)


def test_token_estimate_handles_chinese_and_code() -> None:
    """The deterministic character estimate assigns the configured script weights."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 15) == 4
    assert estimate_tokens("汉字示") == 4
    assert estimate_tokens("a" * 15 + "汉字示") == 8


def test_pack_merges_adjacent_lines_and_counts_full_files_once() -> None:
    """Overlapping lines keep the higher-score content and adjacent lines form one fragment."""
    results = [
        _hit("one.py", 2, "duplicate\nthird", 0.5),
        _hit("one.py", 1, "first\nsecond", 0.9),
        _hit("two.py", 1, "another", 0.8),
        _hit("one.py", 4, "fourth", 0.4),
    ]
    sizes = {"one.py": 100, "two.py": 30}
    packed = pack_chunks_to_budget(results, None, file_token_count=sizes.get)
    assert [row.content for row in packed.fragments] == ["first\nsecond\nthird\nfourth", "another"]
    assert (packed.fragments[0].start_line, packed.fragments[0].end_line) == (1, 4)
    assert packed.packed_tokens == sum(estimate_tokens(row.content) for row in packed.fragments)
    assert packed.full_file_tokens == packed.grep_estimated_tokens == 130
    assert packed.savings_pct == pytest.approx(100 * (130 - packed.packed_tokens) / 130)


def test_pack_skips_oversized_chunks_and_handles_zero_and_unknown_baselines() -> None:
    """A lower-ranked chunk can fill an available budget after a larger chunk is declined."""
    results = [_hit("long.py", 1, "字" * 20, 0.9), _hit("short.py", 1, "short", 0.8)]
    packed = pack_chunks_to_budget(results, 2)
    assert [row.file_path for row in packed.fragments] == ["short.py"]
    assert packed.packed_tokens == 2
    assert packed.full_file_tokens is None
    assert packed.savings_pct is None
    assert pack_chunks_to_budget(results, 0).fragments == []
    with pytest.raises(ValueError, match="non-negative"):
        pack_chunks_to_budget(results, -1)

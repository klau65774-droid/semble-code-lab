from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from time import perf_counter

import numpy as np
import numpy.typing as npt
from model2vec import StaticModel

from semble.context_packer import estimate_tokens, pack_chunks_to_budget
from semble.index.bm25 import BM25
from semble.index.create import build_bilingual_bm25
from semble.index.dense import SelectableBasicBackend
from semble.index.sparse import selector_to_mask
from semble.ranking import apply_query_boost, boost_multi_chunk_files, rerank_topk, resolve_alpha
from semble.ranking.boosting import detect_symbols, is_symbol_query
from semble.ranking.penalties import RankedChunk, rank_with_penalties
from semble.security import redact_range, scan_and_redact_text
from semble.tokens import expand_cjk_concepts, needs_bilingual_index, tokenize
from semble.types import (
    Chunk,
    ChunkPreview,
    ExplainedSearchResponse,
    ExplainedSearchResult,
    QueryType,
    ScoreBreakdown,
    SearchMode,
    SearchResult,
)

_RRF_K = 60
_CANDIDATE_MULTIPLIER = 5


@dataclass(slots=True)
class _BoostTrace:
    coherence: dict[Chunk, float] = field(default_factory=dict)
    query: dict[Chunk, float] = field(default_factory=dict)
    reasons: dict[Chunk, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class _Channel:
    raw: dict[Chunk, float]
    ranks: dict[Chunk, int]
    rrf: dict[Chunk, float]

    @classmethod
    def from_results(cls, results: list[SearchResult]) -> "_Channel":
        """Convert one retrieval channel's raw scores to ranked reciprocal scores."""
        raw = {result.chunk: result.score for result in results}
        rrf = _rrf_scores(raw)
        return cls(raw, {chunk: rank for rank, chunk in enumerate(rrf, 1)}, rrf)


def _rrf_scores(scores: dict[Chunk, float]) -> dict[Chunk, float]:
    """Convert raw scores to RRF scores 1/(k + rank); higher raw score → rank 1."""
    if not scores:
        return scores
    ranked = sorted(scores, key=lambda c: -scores[c])
    return {chunk: 1.0 / (_RRF_K + rank) for rank, chunk in enumerate(ranked, 1)}


def _search_semantic(
    query: str,
    model: StaticModel,
    semantic_index: SelectableBasicBackend,
    chunks: list[Chunk],
    top_k: int,
    selector: npt.NDArray[np.int_] | None,
    *,
    skip_empty_embedding: bool = False,
) -> list[SearchResult]:
    """Run semantic search for a query."""
    query_embedding = model.encode([query])
    if skip_empty_embedding and not query_embedding.any():
        return []
    indices, scores = semantic_index.query(query_embedding, k=top_k, selector=selector)[0]
    # Vicinity returns cosine distance; convert to similarity so higher = better.
    return [SearchResult(chunk=chunks[index], score=1.0 - float(distance)) for index, distance in zip(indices, scores)]


def _sort_top_k(arr: npt.NDArray, top_k: int) -> npt.NDArray[np.int_]:
    """Get the top k indices of an array in sort order."""
    neg_arr = -arr
    if top_k >= len(arr):
        return np.argsort(neg_arr)
    partitioned = np.argpartition(neg_arr, kth=top_k)[:top_k]
    return partitioned[np.argsort(neg_arr[partitioned])]


def _search_bm25(
    query: str,
    bm25_index: BM25,
    chunks: list[Chunk],
    top_k: int,
    selector: npt.NDArray[np.int_] | None,
) -> list[SearchResult]:
    """Return chunks ranked by BM25 score, excluding zero-score results."""
    results, _ = _bm25_candidates(tokenize(query), bm25_index, chunks, top_k, selector)
    return results


def _bm25_candidates(
    tokens: list[str],
    bm25_index: BM25,
    chunks: list[Chunk],
    top_k: int,
    selector: npt.NDArray[np.int_] | None,
) -> tuple[list[SearchResult], int]:
    """Retrieve top BM25 candidates and count all positive matches in the selected corpus."""
    if not tokens:
        return [], 0
    mask = selector_to_mask(selector, len(chunks))
    scores: npt.NDArray[np.float32] = bm25_index.get_scores(tokens, weight_mask=mask)
    indices = _sort_top_k(scores, top_k)

    # Exclude chunks with zero score, no query tokens matched.
    results = [SearchResult(chunk=chunks[i], score=float(scores[i])) for i in indices if scores[i] > 0]
    return results, int(np.count_nonzero(scores > 0))


def _fuse_rrf(
    semantic: dict[Chunk, float],
    lexical: dict[Chunk, float],
    alpha: float,
    *,
    enhanced: bool = False,
) -> dict[Chunk, float]:
    """Fuse semantic and lexical ranks, preserving the upstream baseline tie ordering."""
    candidates = {*semantic, *lexical}
    if enhanced:
        ordered = sorted(candidates, key=lambda c: (c.file_path, c.start_line, c.end_line, c.content))
    else:
        ordered = sorted(candidates, key=lambda c: c.start_line)
    combined = {chunk: alpha * semantic.get(chunk, 0.0) + (1.0 - alpha) * lexical.get(chunk, 0.0) for chunk in ordered}
    return {chunk: score for chunk, score in combined.items() if score}


def _rank_fused(
    scores: dict[Chunk, float],
    query: str,
    chunks: list[Chunk],
    top_k: int,
    *,
    rerank: bool,
    penalise_paths: bool,
    enhanced: bool = False,
    trace: _BoostTrace | None = None,
) -> list[RankedChunk]:
    """Apply the shared boost and penalty stages, keeping actual score deltas when requested."""
    if not rerank:
        return [RankedChunk(chunk, score) for chunk, score in sorted(scores.items(), key=lambda row: -row[1])[:top_k]]

    with_coherence = scores.copy()
    boost_multi_chunk_files(with_coherence)
    boosted = apply_query_boost(
        with_coherence, query, chunks, enhanced=enhanced, reasons=trace.reasons if trace is not None else None
    )
    if trace is None:
        ranked = rerank_topk(boosted, top_k, penalise_paths=penalise_paths)
        return [RankedChunk(chunk, score) for chunk, score in ranked]
    trace.coherence = {chunk: score - scores[chunk] for chunk, score in with_coherence.items()}
    trace.query = {chunk: score - with_coherence.get(chunk, 0.0) for chunk, score in boosted.items()}
    return rank_with_penalties(boosted, top_k, penalise_paths=penalise_paths)


def search(
    query: str,
    model: StaticModel,
    semantic_index: SelectableBasicBackend,
    bm25_index: BM25,
    chunks: list[Chunk],
    top_k: int,
    alpha: float | None = None,
    selector: npt.NDArray[np.int_] | None = None,
    rerank: bool = True,
) -> list[SearchResult]:
    """Hybrid search: alpha-weighted combination of semantic and BM25 scores.

    Both score sets are converted to RRF scores before combining, so alpha has
    a consistent meaning regardless of raw score magnitude.

    :param query: Search query string.
    :param model: Embedding model for semantic search.
    :param semantic_index: Pre-built semantic (vector) index.
    :param bm25_index: Pre-built BM25 index.
    :param chunks: All indexed chunks (parallel to BM25 index).
    :param top_k: Number of results to return.
    :param alpha: Weight for semantic score (1-alpha goes to BM25). None = auto-detect based on query type.
    :param selector: Optional array of chunk indices to filter results by.
    :param rerank: Whether to perform code-tuned reranking. On by default for code search, off for docs search.
    :return: List of search results sorted by combined score descending.
    """
    alpha_weight = resolve_alpha(query, alpha)

    # Over-fetch candidates so the merged pool is large enough after union and re-ranking.
    candidate_count = top_k * _CANDIDATE_MULTIPLIER

    semantic = _search_semantic(query, model, semantic_index, chunks, candidate_count, selector)
    semantic_scores: dict[Chunk, float] = {result.chunk: result.score for result in semantic}
    bm25_scores = {
        result.chunk: result.score for result in _search_bm25(query, bm25_index, chunks, candidate_count, selector)
    }

    combined = _fuse_rrf(_rrf_scores(semantic_scores), _rrf_scores(bm25_scores), alpha_weight)
    ranked = _rank_fused(combined, query, chunks, top_k, rerank=rerank, penalise_paths=alpha_weight < 1.0)
    return [SearchResult(chunk=row.chunk, score=row.score) for row in ranked]


def _retrieve_channels(
    semantic_query: str,
    tokens: list[str],
    model: StaticModel,
    semantic_index: SelectableBasicBackend,
    bm25_index: BM25,
    bilingual_bm25_index: BM25 | None,
    chunks: list[Chunk],
    candidate_count: int,
    selector: npt.NDArray[np.int_] | None,
    mode: SearchMode,
    *,
    use_bilingual: bool = False,
) -> tuple[_Channel, _Channel, int]:
    """Retrieve only the channels needed by the chosen mode."""
    if not chunks or not semantic_query.strip() or (selector is not None and not selector.size):
        return _Channel.from_results([]), _Channel.from_results([]), 0

    semantic = (
        _search_semantic(
            semantic_query,
            model,
            semantic_index,
            chunks,
            candidate_count,
            selector,
            skip_empty_embedding=mode == "enhanced",
        )
        if mode != "bm25"
        else []
    )
    sparse: list[SearchResult] = []
    hits = 0
    if mode != "semantic":
        lexical_index = bm25_index
        if use_bilingual and tokens:
            lexical_index = bilingual_bm25_index or build_bilingual_bm25(chunks, bm25_index.doc_order)
        sparse, hits = _bm25_candidates(tokens, lexical_index, chunks, candidate_count, selector)
    return _Channel.from_results(semantic), _Channel.from_results(sparse), hits


def _query_type(query: str, symbols: list[str]) -> QueryType:
    """Classify a query by the same symbol detection used in ranking."""
    if is_symbol_query(query):
        return "symbol"
    return "embedded_symbol" if symbols else "natural_language"


def _search_alpha(query: str, mode: SearchMode, alpha: float | None) -> float:
    """Resolve the hybrid weight or use a fixed weight for a single-channel search."""
    if mode == "semantic":
        return 1.0
    if mode == "bm25":
        return 0.0
    return resolve_alpha(query, alpha, enhanced=mode == "enhanced")


def _redacted_previews(
    ranked: list[RankedChunk], chunks: list[Chunk], previews: Mapping[Chunk, ChunkPreview] | None
) -> Mapping[Chunk, ChunkPreview]:
    """Use available previews or scan the indexed chunk stream for each selected file."""
    missing_paths = {row.chunk.file_path for row in ranked if previews is None or row.chunk not in previews}
    if not missing_paths:
        return previews or {}
    by_file: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.file_path in missing_paths:
            by_file[chunk.file_path].append(chunk)
    resolved = dict(previews or {})
    for siblings in by_file.values():
        resolved.update(_redact_chunk_stream(siblings))
    return resolved


def _redact_chunk_stream(chunks: list[Chunk]) -> dict[Chunk, ChunkPreview]:
    """Preserve snapshot order to detect credentials spanning multiple AST chunks."""
    parts = []
    spans = []
    offset = 0
    last_line = chunks[0].start_line
    for chunk in chunks:
        if chunk.start_line > last_line:
            parts.append("\n")
            offset += 1
        parts.append(chunk.content)
        end = offset + len(chunk.content)
        spans.append((offset, end))
        offset = end
        last_line = chunk.start_line + chunk.content.count("\n")

    source = "".join(parts)
    _, findings = scan_and_redact_text(source)
    return {
        chunk: ChunkPreview(*redact_range(source, findings, start, end))
        for chunk, (start, end) in zip(chunks, spans, strict=True)
    }


def _explain_result(
    ranked: RankedChunk,
    rank: int,
    chunk_id: str,
    alpha: float,
    semantic: _Channel,
    lexical: _Channel,
    fused: dict[Chunk, float],
    trace: _BoostTrace,
    preview: ChunkPreview,
) -> ExplainedSearchResult:
    """Render a selected result with its exact ranking factors and a safe code preview."""
    chunk = ranked.chunk
    coherence = trace.coherence.get(chunk, 0.0)
    reasons = (["file_coherence"] if coherence else []) + trace.reasons.get(chunk, [])
    breakdown = ScoreBreakdown(
        semantic_raw=semantic.raw.get(chunk, 0.0),
        semantic_rank=semantic.ranks.get(chunk),
        semantic_rrf=semantic.rrf.get(chunk, 0.0),
        bm25_raw=lexical.raw.get(chunk, 0.0),
        bm25_rank=lexical.ranks.get(chunk),
        bm25_rrf=lexical.rrf.get(chunk, 0.0),
        alpha_weight=alpha,
        fused_rrf=fused.get(chunk, 0.0),
        multi_chunk_boost=coherence,
        query_boost=trace.query.get(chunk, 0.0),
        boost_reasons=reasons,
        path_penalty=ranked.path_penalty,
        saturation_decay=ranked.saturation_decay,
        final_score=ranked.score,
    )
    return ExplainedSearchResult(
        chunk=replace(chunk, content=preview.content),
        chunk_id=chunk_id,
        rank=rank,
        score=ranked.score,
        breakdown=breakdown,
        estimated_tokens=estimate_tokens(preview.content),
        redacted_content=preview.content,
        secrets_redacted=preview.secrets_redacted,
    )


def search_explained(
    query: str,
    model: StaticModel,
    semantic_index: SelectableBasicBackend,
    bm25_index: BM25,
    chunks: list[Chunk],
    top_k: int = 10,
    *,
    mode: SearchMode = "enhanced",
    alpha: float | None = None,
    selector: npt.NDArray[np.int_] | None = None,
    rerank: bool = True,
    token_budget: int | None = None,
    bilingual_bm25_index: BM25 | None = None,
    previews: Mapping[Chunk, ChunkPreview] | None = None,
    file_token_count: Callable[[str], int | None] | None = None,
) -> ExplainedSearchResponse:
    """Return ranked hits with scoring factors and a separately budgeted context.

    Both hybrid modes use the same stored chunks and dense embeddings. Single-channel
    searches skip boosts and penalties and express their scores as reciprocal ranks.
    """
    if top_k < 1:
        raise ValueError("top_k must be positive")
    start = perf_counter()
    query, _ = scan_and_redact_text(query)
    enhanced = mode == "enhanced"
    use_bilingual = mode != "baseline" and needs_bilingual_index(query)
    tokens = tokenize(query, multilingual=use_bilingual)
    concept_terms = expand_cjk_concepts(query) if enhanced else []
    lexical_tokens = list(dict.fromkeys([*tokens, *concept_terms])) if concept_terms else tokens
    semantic_query = f"{query} {' '.join(concept_terms)}" if concept_terms else query
    symbols = detect_symbols(query, enhanced=mode != "baseline")
    alpha_weight = _search_alpha(query, mode, alpha)
    hybrid = mode in ("enhanced", "baseline")
    candidate_count = top_k * _CANDIDATE_MULTIPLIER if hybrid else top_k
    semantic, lexical, bm25_hits = _retrieve_channels(
        semantic_query,
        lexical_tokens,
        model,
        semantic_index,
        bm25_index,
        bilingual_bm25_index,
        chunks,
        candidate_count,
        selector,
        mode,
        use_bilingual=use_bilingual,
    )
    fused = _fuse_rrf(semantic.rrf, lexical.rrf, alpha_weight, enhanced=mode != "baseline")
    definition_chunks = chunks if selector is None else [chunks[i] for i in selector]
    trace = _BoostTrace()
    ranked = _rank_fused(
        fused,
        query,
        definition_chunks,
        top_k,
        rerank=hybrid and rerank,
        penalise_paths=enhanced or alpha_weight < 1.0,
        enhanced=enhanced,
        trace=trace,
    )
    ids = dict(zip(chunks, bm25_index.doc_order))
    safe_previews = _redacted_previews(ranked, chunks, previews)
    results = [
        _explain_result(
            row,
            rank,
            ids[row.chunk],
            alpha_weight,
            semantic,
            lexical,
            fused,
            trace,
            safe_previews[row.chunk],
        )
        for rank, row in enumerate(ranked, 1)
    ]
    packed = pack_chunks_to_budget(results, token_budget, file_token_count=file_token_count)
    return ExplainedSearchResponse(
        query=query,
        mode=mode,
        query_type=_query_type(query, symbols),
        tokens=lexical_tokens,
        detected_symbols=symbols,
        alpha_used=alpha_weight,
        latency_ms=(perf_counter() - start) * 1000,
        results=results,
        packed_tokens=packed.packed_tokens,
        full_file_tokens=packed.full_file_tokens,
        savings_pct=packed.savings_pct,
        grep_estimated_tokens=packed.grep_estimated_tokens,
        bm25_hits=bm25_hits,
        packed_context=packed.fragments,
    )

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil, log2
from statistics import mean
from typing import TYPE_CHECKING

from semble.server.models import (
    BenchmarkMetrics,
    BenchmarkQuery,
    BenchmarkQueryMetrics,
    BenchmarkResponse,
    SearchRequest,
)
from semble.types import ExplainedSearchResponse, SearchMode

if TYPE_CHECKING:
    from semble.server.service import Repository

_MODES: tuple[SearchMode, ...] = ("enhanced", "baseline", "semantic", "bm25")
_TOP_K = 10


@dataclass(frozen=True, slots=True)
class Case:
    repo_id: str
    category: str
    query: str
    targets: tuple[tuple[str, str], ...]


_CASES = (
    Case(
        "semble-core",
        "embedded_symbol",
        "where is enrich_for_bm25 defined",
        (("index/sparse.py", "def enrich_for_bm25("),),
    ),
    Case(
        "semble-core",
        "chinese",
        "混合检索和重排序打分逻辑",
        (
            ("search.py", "def search("),
            ("search.py", "def _rank_fused("),
            ("ranking/penalties.py", "def rank_with_penalties("),
        ),
    ),
    Case(
        "semble-core",
        "english",
        "how is a saved index invalidated when a source file changes",
        (("cache.py", "def get_validated_cache("),),
    ),
    Case(
        "semble-core",
        "english",
        "fall back to splitting source by lines when no parser is available",
        (("chunking/chunking.py", "if chunk_boundaries is None:"),),
    ),
    Case(
        "semble-core",
        "embedded_symbol",
        "where is DEFAULT_MODEL_NAME configured",
        (("utils.py", "DEFAULT_MODEL_NAME ="),),
    ),
    Case(
        "semble-core", "mixed", "增量索引里 BM25.set_doc_order 如何重排文档", (("index/bm25.py", "def set_doc_order("),)
    ),
    Case(
        "semble-core",
        "english",
        "reduce repeat hits from a single file using score decay",
        (("ranking/penalties.py", "excess = max("),),
    ),
    Case(
        "semble-core",
        "english",
        "reuse embeddings for unchanged files during incremental indexing",
        (("index/create.py", "reused_parts.append("),),
    ),
    Case(
        "semble-core",
        "english",
        "detect source language from file extensions",
        (("index/files.py", "def detect_language("),),
    ),
    Case("bilingual-demo", "mixed", "中文测试 cache_key 索引缓存路径", (("services/cache.py", "def cache_key("),)),
    Case("bilingual-demo", "chinese", "哪里生成租户隔离的缓存键并计算摘要", (("services/cache.py", "def cache_key("),)),
    Case(
        "bilingual-demo",
        "chinese",
        "响应缓存按单调时钟判断过期时间",
        (("services/cache.py", "if monotonic() >= expires_at:"),),
    ),
    Case(
        "bilingual-demo",
        "chinese",
        "网关错误 502 和频率限制 429 怎样重试",
        (("services/retry.py", "def retry_delay("),),
    ),
    Case(
        "bilingual-demo", "go", "where is RateLimiter defined", (("ratelimit/limiter.go", "type RateLimiter struct"),)
    ),
    Case(
        "bilingual-demo",
        "go",
        "protect tenant counters with a mutex and reset an expired window",
        (("ratelimit/limiter.go", "limiter.mu.Lock()"),),
    ),
    Case(
        "bilingual-demo",
        "typescript",
        "where is RequestRouter.dispatch defined",
        (("gateway/router.ts", "public async dispatch("),),
    ),
    Case(
        "bilingual-demo",
        "typescript",
        "what does fetchWithTimeout do when the timer expires",
        (("gateway/client.ts", "export async function fetchWithTimeout("),),
    ),
    Case("bilingual-demo", "chinese", "租户身份缺失时怎样拒绝路由", (("gateway/router.ts", "if (!request.tenantId)"),)),
    Case(
        "bilingual-demo",
        "sql",
        "where is request_cache defined with the tenant primary key",
        (("storage/schema.sql", "CREATE TABLE request_cache ("),),
    ),
    Case("bilingual-demo", "sql", "清理已经过期的缓存记录", (("storage/queries.sql", "DELETE FROM request_cache"),)),
    Case("bilingual-demo", "sql", "按租户检索仍然有效的缓存内容", (("storage/queries.sql", "SELECT response_body"),)),
    Case(
        "bilingual-demo",
        "mixed",
        "网关请求追踪标识 timeoutMs",
        (("gateway/client.ts", "export async function fetchWithTimeout("), ("docs/gateway.md", "租户请求沿着路由")),
    ),
)


def _resolve_relevance(case: Case, repo: Repository) -> set[str]:
    """Bind annotated source anchors to the chunks in this repository snapshot."""
    relevant = set()
    for path, anchor in case.targets:
        matches = [
            repo.chunk_ids[chunk]
            for chunk in repo.files[path].chunks
            if any(line.strip().startswith(anchor) for line in chunk.content.splitlines())
        ]
        if not matches:
            raise ValueError("Benchmark relevance anchor missing")
        relevant.update(matches)
    return relevant


def _measure(response: ExplainedSearchResponse, relevant: set[str]) -> BenchmarkQueryMetrics:
    """Score one ranked list against independently annotated relevant chunks."""
    ranked = [result.chunk_id for result in response.results]
    hit_positions = [rank for rank, chunk_id in enumerate(ranked, 1) if chunk_id in relevant]
    dcg = sum(1.0 / log2(rank + 1) for rank in hit_positions)
    ideal = sum(1.0 / log2(rank + 1) for rank in range(1, min(_TOP_K, len(relevant)) + 1))
    return BenchmarkQueryMetrics(
        ndcg_at_10=dcg / ideal,
        mrr_at_10=1.0 / hit_positions[0] if hit_positions else 0.0,
        recall_at_5=len(relevant.intersection(ranked[:5])) / len(relevant),
        latency_ms=response.latency_ms,
        token_savings_pct=response.savings_pct or 0.0,
        ranked_chunk_ids=ranked,
        bm25_hits=response.bm25_hits,
    )


def _summarize(rows: list[BenchmarkQueryMetrics]) -> BenchmarkMetrics:
    """Macro-average retrieval and token metrics and report nearest-rank p95 latency."""
    latency = sorted(row.latency_ms for row in rows)
    return BenchmarkMetrics(
        ndcg_at_10=mean(row.ndcg_at_10 for row in rows),
        mrr_at_10=mean(row.mrr_at_10 for row in rows),
        recall_at_5=mean(row.recall_at_5 for row in rows),
        p95_latency_ms=latency[ceil(len(latency) * 0.95) - 1],
        avg_token_savings_pct=mean(row.token_savings_pct for row in rows),
    )


def run_benchmark(repos: Mapping[str, Repository]) -> BenchmarkResponse:
    """Run the same locally annotated queries across all four retrieval modes."""
    rows = []
    for case in _CASES:
        repo = repos[case.repo_id]
        relevant = _resolve_relevance(case, repo)
        request = SearchRequest(repo_id=case.repo_id, query=case.query, top_k=_TOP_K, compare_baseline=False)
        scores = {mode: _measure(repo.search(request, mode), relevant) for mode in _MODES}
        rows.append(BenchmarkQuery(case.repo_id, case.category, case.query, sorted(relevant), scores))
    scores_by_mode = {mode: _summarize([row.modes[mode] for row in rows]) for mode in _MODES}
    return BenchmarkResponse(len(rows), scores_by_mode, rows)

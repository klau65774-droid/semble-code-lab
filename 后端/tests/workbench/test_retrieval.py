import json
from pathlib import Path

import pytest

from semble.index import SembleIndex
from semble.ranking.boosting import apply_query_boost, detect_symbols, resolve_alpha
from semble.tokens import cjk_ratio, expand_cjk_concepts, tokenize, tokenize_bilingual
from semble.types import Chunk
from tests.conftest import make_chunk


def test_bilingual_tokenization_preserves_legacy_ascii() -> None:
    """ASCII compatibility, 3-4 digit codes, CJK adjacency and stop-word boundaries are independent."""
    text = "如何设置cache_key和重试429错误 502 与 0 1 25 99"
    assert tokenize(text) == ["cache_key", "cache", "key"]
    actual = tokenize_bilingual(text)
    assert actual == tokenize(text, multilingual=True)
    assert actual == [
        "设",
        "置",
        "设置",
        "cache_key",
        "cache",
        "key",
        "重",
        "试",
        "重试",
        "429",
        "错",
        "误",
        "错误",
        "502",
    ]
    assert tokenize_bilingual("的了和与在是如何怎么哪里") == []
    assert tokenize_bilingual("检索和排序") == ["检", "索", "检索", "排", "序", "排序"]
    assert tokenize_bilingual("CacheKey") == ["cachekey", "cache", "key"]
    assert cjk_ratio("how does hybrid search work") == 0.0
    assert cjk_ratio("混合检索") == 1.0
    assert expand_cjk_concepts("hybrid search") == []
    assert expand_cjk_concepts("混合检索和重排序打分逻辑") == [
        "hybrid",
        "search",
        "retrieval",
        "rerank",
        "score",
        "scoring",
    ]


@pytest.mark.parametrize(
    ("query", "symbols", "alpha"),
    [
        ("cache_key", ["cache_key"], 0.30),
        ("where is enrich_for_bm25 defined", ["enrich_for_bm25"], 0.40),
        ("中文cache_key缓存规则", ["cache_key"], 0.30),
        ("比较DEFAULT_MODEL_NAME和pkg.func与A::B", ["DEFAULT_MODEL_NAME", "pkg.func", "A::B"], 0.30),
        ("查看HTTPServer及getHTTPResponse", ["HTTPServer", "getHTTPResponse"], 0.30),
        ("where is 123cache_key defined", [], 0.50),
        ("how does hybrid search work", [], 0.50),
        ("混合检索和重排序打分逻辑", [], 0.20),
        ("网关错误 502 和频率限制 429 怎样重试", [], 0.20),
    ],
)
def test_symbol_classification(query: str, symbols: list[str], alpha: float) -> None:
    """Enhanced symbols have ASCII-only boundaries and use the configured automatic weights."""
    assert detect_symbols(query, enhanced=True) == symbols
    assert resolve_alpha(query, None, enhanced=True) == alpha
    assert resolve_alpha(query, 0.82, enhanced=True) == 0.82
    assert resolve_alpha("where is enrich_for_bm25 defined", None) == 0.50


@pytest.mark.parametrize(
    ("symbol", "definition", "language"),
    [
        ("enrich_for_bm25", "def enrich_for_bm25(): pass", "python"),
        ("DEFAULT_MODEL_NAME", 'DEFAULT_MODEL_NAME: str = "demo"', "python"),
        ("pkg.func_name", "def func_name(): pass", "python"),
        ("A::B", "class B: pass", "python"),
        ("RequestRouter.dispatch", "  public async dispatch(request: Request) {", "typescript"),
        ("RateLimiter.Allow", "func (limiter *RateLimiter) Allow(tenant string) bool {", "go"),
        ("REQUEST_CACHE", "CREATE TABLE request_cache (tenant_id TEXT);", "sql"),
    ],
)
def test_recall_definitions_outside_candidates(symbol: str, definition: str, language: str) -> None:
    """Recall actual bindings in files whose names have no overlap with the queried symbol."""
    candidate = make_chunk(f"print({symbol!r})", "lookup.py")
    defining = Chunk(definition, "impl", 1, 1, language)
    reasons = {}
    query = f"请查看{symbol}的定义"
    boosted = apply_query_boost({candidate: 0.5}, query, [candidate, defining], enhanced=True, reasons=reasons)
    assert boosted[defining] > boosted[candidate]
    assert reasons[defining] == ["embedded_symbol_definition"]


@pytest.fixture
def code_index(tmp_path: Path, local_model: Path, monkeypatch: pytest.MonkeyPatch) -> SembleIndex:
    """Index a bilingual code corpus with a reusable registered model artifact."""
    monkeypatch.setenv("SEMBLE_CACHE_LOCATION", str(tmp_path / "cache"))
    monkeypatch.setenv("SEMBLE_MODEL_NAME", str(local_model))
    source = tmp_path / "workspace"
    (source / "tests").mkdir(parents=True)
    (source / "store.py").write_text(
        'def cache_key(path):\n    """租户隔离缓存生成请求标识。"""\n    return path\n', encoding="utf-8"
    )
    (source / "tests" / "test_store.py").write_text(
        "def test_cache():\n    return cache_key('/api')\n", encoding="utf-8"
    )
    (source / "usage.ts").write_text("export const key = cache_key('/api');\n", encoding="utf-8")
    return SembleIndex.from_path(source)


def test_baseline_agrees_with_upstream_entry_point(code_index: SembleIndex) -> None:
    """Explanation uses exactly the legacy query weights, stages and scores in baseline mode."""
    query = "where is cache_key defined"
    baseline = code_index.search_explained(query, mode="baseline")
    legacy = code_index.search(query)
    assert [(row.chunk, row.score) for row in baseline.results] == [(row.chunk, row.score) for row in legacy]
    assert baseline.detected_symbols == []
    assert baseline.alpha_used == 0.5


def test_bilingual_index_survives_legacy_cache_roundtrip(code_index: SembleIndex, tmp_path: Path) -> None:
    """A persisted ASCII index can derive bilingual postings without replacing its legacy cache format."""
    path = tmp_path / "saved"
    code_index.save(path)
    loaded = SembleIndex.load_from_disk(path)
    query = "租户隔离的请求标识"
    assert loaded.search_explained(query, mode="baseline").bm25_hits == 0
    enhanced = loaded.search_explained(query)
    assert enhanced.bm25_hits == 1
    assert enhanced.results[0].chunk.file_path == "store.py"
    assert enhanced.alpha_used == 0.20
    assert enhanced.full_file_tokens == loaded.search_explained(query, top_k=1).full_file_tokens
    assert enhanced.full_file_tokens and enhanced.packed_tokens > 0


@pytest.mark.parametrize("mode", ["enhanced", "baseline", "semantic", "bm25"])
def test_score_breakdown_reconstructs_each_ranking_stage(code_index: SembleIndex, mode: str) -> None:
    """Raw channels, boosts, selection factors and final values remain JSON-serializable."""
    result = code_index.search_explained("find cache_key", mode=mode)
    assert result.results
    assert json.loads(json.dumps(result.to_dict()))["mode"] == mode
    for hit in result.results:
        row = hit.breakdown
        assert row.fused_rrf == pytest.approx(
            row.alpha_weight * row.semantic_rrf + (1 - row.alpha_weight) * row.bm25_rrf
        )
        assert hit.score == row.final_score
        assert row.final_score == pytest.approx(
            (row.fused_rrf + row.multi_chunk_boost + row.query_boost) * row.path_penalty * row.saturation_decay
        )
        if mode in ("semantic", "bm25"):
            assert row.path_penalty == row.saturation_decay == 1.0
            assert row.multi_chunk_boost == row.query_boost == 0.0
    if mode == "enhanced":
        top = result.results[0]
        assert top.chunk.file_path == "store.py"
        assert top.breakdown.query_boost > 0
        assert "embedded_symbol_definition" in top.breakdown.boost_reasons
        assert any(hit.breakdown.path_penalty == 0.3 for hit in result.results)
    if mode == "semantic":
        assert result.alpha_used == 1.0
        assert result.bm25_hits == 0
        assert all(hit.breakdown.bm25_rank is None for hit in result.results)
    if mode == "bm25":
        assert result.alpha_used == 0.0
        assert all(hit.breakdown.semantic_rank is None for hit in result.results)


def test_filter_is_enforced_for_non_candidate_definition_boosts(code_index: SembleIndex) -> None:
    """Definition recall stays within the selected language and unknown languages return no hits."""
    display = code_index.search_explained("cache_key", filter_languages=["typescript"])
    assert display.results
    assert all(row.chunk.language == "typescript" for row in display.results)
    assert code_index.search_explained("cache_key", filter_languages=["unknown"]).results == []


def test_no_rerank_keeps_the_fused_score(code_index: SembleIndex) -> None:
    """Disabling reranking removes both additive and multiplicative adjustments."""
    response = code_index.search_explained("cache_key", rerank=False, token_budget=0)
    assert response.packed_tokens == 0
    assert response.packed_context == []
    for result in response.results:
        assert result.breakdown.fused_rrf == result.score
        assert result.breakdown.boost_reasons == []


def test_explained_previews_mask_cross_chunk_secrets_and_report_file_decay(
    tmp_path: Path, local_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A local library index masks multi-chunk keys and records each selected chunk's actual decay."""
    monkeypatch.setenv("SEMBLE_CACHE_LOCATION", str(tmp_path / "cache"))
    monkeypatch.setenv("SEMBLE_MODEL_NAME", str(local_model))
    root = tmp_path / "repo"
    root.mkdir()
    marker = "SYNTHETIC_ONLY_PRIVATE_ROW"
    body = "".join(f"# cache {marker}{i:02d}{'X' * 40}\n" for i in range(40))
    text = "# -----BEGIN PRIVATE KEY-----\n" + body + "# -----END PRIVATE KEY-----\n"
    (root / "preview.py").write_text(text, encoding="utf-8")
    response = SembleIndex.from_path(root).search_explained("cache")
    assert len(response.results) >= 3
    assert any(row.breakdown.saturation_decay < 1 for row in response.results)
    assert all(marker not in row.chunk.content for row in response.results)
    assert all(row.secrets_redacted == 1 for row in response.results)
    assert marker not in json.dumps(response.to_dict())


def test_chinese_query_retrieves_english_only_code(
    tmp_path: Path, local_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pure Chinese technical queries expand into English SE concepts for English-only repositories."""
    monkeypatch.setenv("SEMBLE_CACHE_LOCATION", str(tmp_path / "cache"))
    monkeypatch.setenv("SEMBLE_MODEL_NAME", str(local_model))
    root = tmp_path / "english_repo"
    root.mkdir()
    (root / "limiter.py").write_text(
        "class RateLimiter:\n    def check_rate_limit(self, tenant: str) -> bool:\n        return True\n",
        encoding="utf-8",
    )
    (root / "routing.py").write_text(
        "def dispatch_route(path: str) -> str:\n    return path\n",
        encoding="utf-8",
    )
    (root / "middleware.py").write_text(
        "def cors_middleware(origin: str) -> bool:\n    return origin == '*'\n",
        encoding="utf-8",
    )
    index = SembleIndex.from_path(root)
    query = "限流频率控制中间件路由在哪里"
    baseline = index.search_explained("如何限流并检查频率", mode="baseline")
    assert baseline.bm25_hits == 0
    enhanced = index.search_explained("租户限流频率控制", mode="enhanced")
    assert enhanced.alpha_used == 0.20
    assert enhanced.bm25_hits >= 1
    assert "limiter.py" == enhanced.results[0].chunk.file_path
    assert "ratelimit" in enhanced.tokens
    cors_res = index.search_explained("跨域中间件", mode="enhanced")
    assert cors_res.results[0].chunk.file_path == "middleware.py"
    assert query  # keeps sample query lint clean

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from semble.types import Chunk, ContentType, ExplainedSearchResponse, SearchMode

RepositoryId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
ResultLimit = Annotated[int, Field(ge=1, le=100)]
FilePath = Annotated[str, Field(min_length=1, max_length=4096)]


class ErrorResponse(BaseModel):
    detail: str


class IndexRequest(BaseModel):
    path: FilePath
    repo_id: RepositoryId | None = None
    content_types: Annotated[list[ContentType], Field(min_length=1, max_length=3)] | None = None
    force_rebuild: bool = False


class SearchRequest(BaseModel):
    repo_id: RepositoryId
    query: Annotated[str, Field(min_length=1, max_length=4096)]
    top_k: ResultLimit = 10
    mode: SearchMode = "enhanced"
    alpha: Annotated[float, Field(ge=0, le=1)] | None = None
    rerank: bool = True
    token_budget: Annotated[int, Field(ge=0)] | None = None
    redact_secrets: bool = Field(default=True, description="Recognized credentials are masked for either flag value.")
    compare_baseline: bool = True
    filter_languages: Annotated[list[str], Field(max_length=100)] | None = None


class RelatedRequest(BaseModel):
    repo_id: RepositoryId
    file_path: FilePath
    line: Annotated[int, Field(ge=1)]
    top_k: ResultLimit = 5


@dataclass(frozen=True, slots=True)
class Health:
    status: Literal["ok"]
    model: str
    loaded_repos: list[str]
    uptime_ms: float


@dataclass(frozen=True, slots=True)
class RepoSummary:
    repo_id: str
    name: str
    path: str
    indexed_files: int
    total_chunks: int
    languages: dict[str, int]
    index_ms: float
    content_types: tuple[ContentType, ...]


@dataclass(frozen=True, slots=True)
class FileSummary:
    file_path: str
    language: str | None
    chunk_count: int
    total_lines: int
    estimated_tokens: int
    path_penalty: float
    secrets_detected: int


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk_id: str
    start_line: int
    end_line: int
    content: str
    estimated_tokens: int
    bm25_tokens_preview: list[str]
    secrets_redacted: int


@dataclass(frozen=True, slots=True)
class FileChunks:
    file_path: str
    total_lines: int
    chunks: list[IndexedChunk]


@dataclass(frozen=True, slots=True)
class RelatedResult:
    chunk_id: str
    chunk: Chunk
    score: float
    estimated_tokens: int
    secrets_redacted: int


@dataclass(frozen=True, slots=True)
class RelatedResponse:
    repo_id: str
    file_path: str
    line: int
    results: list[RelatedResult]


@dataclass(frozen=True, slots=True)
class RankDelta:
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    baseline_rank: int | None
    primary_rank: int | None
    rank_delta: int | None


@dataclass(frozen=True, slots=True)
class BaselineComparison(ExplainedSearchResponse):
    rank_deltas: list[RankDelta]


@dataclass(frozen=True, slots=True)
class SearchResponse(ExplainedSearchResponse):
    baseline_comparison: BaselineComparison | None


@dataclass(frozen=True, slots=True)
class AuditFinding:
    file_path: str
    line: int
    rule: str
    severity: str
    redacted_preview: str


@dataclass(frozen=True, slots=True)
class AuditResponse:
    total_findings: int
    files_affected: int
    by_rule: dict[str, int]
    by_severity: dict[str, int]
    findings: list[AuditFinding]


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    ndcg_at_10: float
    mrr_at_10: float
    recall_at_5: float
    p95_latency_ms: float
    avg_token_savings_pct: float


@dataclass(frozen=True, slots=True)
class BenchmarkQueryMetrics:
    ndcg_at_10: float
    mrr_at_10: float
    recall_at_5: float
    latency_ms: float
    token_savings_pct: float
    ranked_chunk_ids: list[str]
    bm25_hits: int


@dataclass(frozen=True, slots=True)
class BenchmarkQuery:
    repo_id: str
    category: str
    query: str
    relevant_chunk_ids: list[str]
    modes: dict[SearchMode, BenchmarkQueryMetrics]


@dataclass(frozen=True, slots=True)
class BenchmarkResponse:
    query_count: int
    metrics: dict[SearchMode, BenchmarkMetrics]
    queries: list[BenchmarkQuery]

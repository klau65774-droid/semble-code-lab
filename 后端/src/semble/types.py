from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal, TypeAlias

import numpy as np
import numpy.typing as npt

EmbeddingMatrix: TypeAlias = npt.NDArray[np.float32]
SearchMode: TypeAlias = Literal["enhanced", "baseline", "semantic", "bm25"]
QueryType: TypeAlias = Literal["symbol", "embedded_symbol", "natural_language"]


class CallType(str, Enum):
    """Call type for token-savings tracking."""

    SEARCH = "search"
    FIND_RELATED = "find_related"


class ContentType(str, Enum):
    """Content type for indexing and search pipeline selection."""

    CODE = "code"
    DOCS = "docs"
    CONFIG = "config"


@dataclass(frozen=True, slots=True)
class Chunk:
    """A single indexable unit of code."""

    content: str
    file_path: str
    start_line: int
    end_line: int
    language: str | None = None

    @property
    def location(self) -> str:
        """File path and line range as a string."""
        return f"{self.file_path}:{self.start_line}-{self.end_line}"

    def to_dict(self) -> dict[str, Any]:
        """Convert the dataclass to a dict."""
        d = asdict(self)
        d["location"] = self.location
        return d

    @classmethod
    def from_dict(cls: type[Chunk], data: dict[str, Any]) -> Chunk:
        """Create a Chunk from a dict."""
        data.pop("location", None)
        return cls(**data)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single search result with score and source."""

    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    semantic_raw: float
    semantic_rank: int | None
    semantic_rrf: float
    bm25_raw: float
    bm25_rank: int | None
    bm25_rrf: float
    alpha_weight: float
    fused_rrf: float
    multi_chunk_boost: float
    query_boost: float
    boost_reasons: list[str]
    path_penalty: float
    saturation_decay: float
    final_score: float


@dataclass(frozen=True, slots=True)
class ChunkPreview:
    content: str
    secrets_redacted: int


@dataclass(frozen=True, slots=True)
class ExplainedSearchResult:
    chunk: Chunk
    chunk_id: str
    rank: int
    score: float
    breakdown: ScoreBreakdown
    estimated_tokens: int
    redacted_content: str
    secrets_redacted: int


@dataclass(frozen=True, slots=True)
class ContextFragment:
    file_path: str
    start_line: int
    end_line: int
    content: str
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class ExplainedSearchResponse:
    query: str
    mode: SearchMode
    query_type: QueryType
    tokens: list[str]
    detected_symbols: list[str]
    alpha_used: float
    latency_ms: float
    results: list[ExplainedSearchResult]
    packed_tokens: int
    full_file_tokens: int | None
    savings_pct: float | None
    grep_estimated_tokens: int | None
    bm25_hits: int
    packed_context: list[ContextFragment]

    def to_dict(self) -> dict[str, Any]:
        """Return the complete response as JSON-compatible values."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Statistics about the current index state."""

    indexed_files: int = 0
    total_chunks: int = 0
    languages: dict[str, int] = field(default_factory=dict)

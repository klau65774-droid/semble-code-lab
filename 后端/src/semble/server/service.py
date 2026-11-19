from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any

from huggingface_hub import try_to_load_from_cache
from model2vec import StaticModel

from semble.context_packer import estimate_tokens
from semble.index import SembleIndex
from semble.index.create import create_index_from_path
from semble.index.sparse import enrich_for_bm25
from semble.ranking.penalties import file_path_penalty
from semble.security import (
    SecretFinding,
    is_safe_index_entry,
    redact_range,
    scan_and_redact_text,
    validate_safe_local_path,
)
from semble.server.benchmark import run_benchmark
from semble.server.models import (
    AuditFinding,
    AuditResponse,
    BenchmarkResponse,
    FileChunks,
    FileSummary,
    Health,
    IndexedChunk,
    IndexRequest,
    RankDelta,
    RelatedRequest,
    RelatedResponse,
    RelatedResult,
    RepoSummary,
    SearchRequest,
)
from semble.tokens import tokenize_bilingual
from semble.types import Chunk, ChunkPreview, ContentType, ExplainedSearchResponse, SearchMode
from semble.utils import resolve_chunk, resolve_model_name

CORE_ROOT = Path(__file__).resolve().parents[1]
_CORE_EXCLUSIONS = frozenset({"server", "context_packer.py", "security.py"})
_DEFAULT_CONTENT = (ContentType.CODE,)
_DEMO_CONTENT = (ContentType.CODE, ContentType.DOCS)


class WorkbenchError(Exception):
    """An expected HTTP failure with a response safe to expose."""

    def __init__(self, status_code: int, message: str) -> None:
        """Store the HTTP status and a message with no request data."""
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class IndexedFile:
    summary: FileSummary
    chunks: list[Chunk]
    findings: list[AuditFinding]


@dataclass(frozen=True, slots=True)
class Repository:
    root: Path
    summary: RepoSummary
    index: SembleIndex
    files: dict[str, IndexedFile]
    previews: dict[Chunk, ChunkPreview]
    chunk_ids: dict[Chunk, str]
    file_tokens: dict[str, int]

    def get_file(self, path: str) -> IndexedFile:
        """Find an indexed repo-relative name without resolving user input on disk."""
        try:
            return self.files[path.replace("\\", "/")]
        except KeyError:
            raise WorkbenchError(404, "Indexed file not found") from None

    def search(self, request: SearchRequest, mode: SearchMode) -> ExplainedSearchResponse:
        """Search against a single snapshot and its cached, sanitized previews."""
        return self.index.search_explained(
            request.query,
            request.top_k,
            mode=mode,
            alpha=request.alpha,
            rerank=request.rerank,
            token_budget=request.token_budget,
            filter_languages=request.filter_languages,
            previews=self.previews,
            file_token_count=self.file_tokens.get,
        )


def _load_offline_model() -> tuple[StaticModel, str]:
    """Load a local model directory or a previously cached Hub model without network I/O."""
    name = resolve_model_name()
    model_dir = Path(name).expanduser()
    if not model_dir.is_dir():
        cached = try_to_load_from_cache(name, "model.safetensors")
        if not isinstance(cached, str):
            raise RuntimeError("No cached embedding model. Set SEMBLE_MODEL_NAME to a local model directory.")
        model_dir = Path(cached).parent
    model = StaticModel.from_pretrained(model_dir.resolve(), force_download=False)
    return model, scan_and_redact_text(name)[0]


def _path_allowed(path: Path, root: Path) -> bool:
    """Exclude private paths and keep workbench fixtures out of the upstream core corpus."""
    if root == CORE_ROOT:
        parts = path.relative_to(root).parts
        if parts and parts[0] in _CORE_EXCLUSIONS:
            return False
    return is_safe_index_entry(path) and not scan_and_redact_text(str(path))[1]


def _project_previews(source: str, chunks: list[Chunk], findings: list[SecretFinding]) -> dict[Chunk, ChunkPreview]:
    """Project whole-file secret spans into the ordered AST chunks, including split credentials."""
    if not findings:
        return {chunk: ChunkPreview(chunk.content, 0) for chunk in chunks}
    positions = [0, *(match.end() for match in re.finditer("\n", source))]
    cursor = 0
    previews = {}
    for chunk in chunks:
        start = source.find(chunk.content, max(cursor, positions[chunk.start_line - 1]))
        if start < 0 or (chunk.start_line < len(positions) and start >= positions[chunk.start_line]):
            raise ValueError("Cannot align an indexed chunk with its source")
        cursor = start + len(chunk.content)
        content, count = redact_range(source, findings, start, cursor)
        previews[chunk] = ChunkPreview(content, count)
    return previews


def _describe_file(source: str, chunks: list[Chunk], findings: list[SecretFinding]) -> IndexedFile:
    """Build the file tree and audit metadata without retaining raw secrets in either."""
    path = chunks[0].file_path
    summary = FileSummary(
        file_path=path,
        language=chunks[0].language,
        chunk_count=len(chunks),
        total_lines=source.count("\n") + int(not source.endswith("\n")),
        estimated_tokens=estimate_tokens(source),
        path_penalty=file_path_penalty(path),
        secrets_detected=len(findings),
    )
    audit = [AuditFinding(path, row.line, row.rule, row.severity, row.redacted_preview) for row in findings]
    return IndexedFile(summary, chunks, audit)


def _build_repo(
    repo_id: str,
    root: Path,
    content: tuple[ContentType, ...],
    model: StaticModel,
    model_name: str,
) -> Repository:
    """Build the index and all public previews from the same source reads."""
    start = perf_counter()
    sources: dict[str, str] = {}
    bm25, dense, chunks, manifest = create_index_from_path(
        root,
        model,
        content=content,
        display_root=root,
        allow_path=lambda path: _path_allowed(path, root),
        on_source=sources.__setitem__,
    )
    index = SembleIndex(model, bm25, dense, chunks, model_name, content=content, manifest=manifest)
    index.prepare_bilingual_search()
    files: dict[str, IndexedFile] = {}
    previews: dict[Chunk, ChunkPreview] = {}
    file_tokens: dict[str, int] = {}
    grouped: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.file_path].append(chunk)
    for path, group in grouped.items():
        source = sources[path]
        _, findings = scan_and_redact_text(source)
        file = _describe_file(source, group, findings)
        files[path.replace("\\", "/")] = file
        previews.update(_project_previews(source, group, findings))
        file_tokens[path] = file.summary.estimated_tokens
    display_path = scan_and_redact_text(str(root))[0]
    summary = RepoSummary(
        repo_id=repo_id,
        name=root.name,
        path=display_path,
        indexed_files=len(files),
        total_chunks=len(chunks),
        languages=dict(Counter(file.summary.language or "text" for file in files.values())),
        index_ms=(perf_counter() - start) * 1000,
        content_types=content,
    )
    chunk_ids = dict(zip(chunks, bm25.doc_order, strict=True))
    return Repository(root, summary, index, files, previews, chunk_ids, file_tokens)


def _generated_repo_id(path: Path) -> str:
    """Generate a stable, URL-safe ID for a local root."""
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", path.name).strip("-_").lower() or "repo"
    digest = sha256(os.path.normcase(str(path)).encode("utf-8")).hexdigest()[:10]
    return f"{name[:50]}-{digest}"


def _rank_deltas(primary: ExplainedSearchResponse, baseline: ExplainedSearchResponse) -> list[RankDelta]:
    """Measure movement by stable chunk ID, including hits visible on only one side."""
    left = {row.chunk_id: row for row in primary.results}
    right = {row.chunk_id: row for row in baseline.results}
    rows = []
    for chunk_id, row in (right | left).items():
        current = left[chunk_id].rank if chunk_id in left else None
        previous = right[chunk_id].rank if chunk_id in right else None
        chunk = row.chunk
        delta = previous - current if current is not None and previous is not None else None
        rows.append(RankDelta(chunk_id, chunk.file_path, chunk.start_line, chunk.end_line, previous, current, delta))
    return rows


class Workbench:
    """Own the loaded repositories and serialize access to the shared CPU model."""

    def __init__(self, demo_root: Path, allowed_roots: Sequence[Path] = ()) -> None:
        """Load the local embedding model and index both built-in repositories."""
        self._started = perf_counter()
        self._lock = RLock()
        core_workspace = CORE_ROOT.parent.parent if CORE_ROOT.parent.name == "src" else CORE_ROOT
        configured_roots = os.getenv("SEMBLE_ALLOWED_ROOTS", "").split(os.pathsep)
        configured = [Path(root).expanduser() for root in configured_roots if root]
        self._allowed_roots = (core_workspace, demo_root, *allowed_roots, *configured)
        self._model, self._model_name = _load_offline_model()
        self._repos = {
            "semble-core": _build_repo("semble-core", CORE_ROOT, _DEFAULT_CONTENT, self._model, self._model_name),
            "bilingual-demo": _build_repo("bilingual-demo", demo_root, _DEMO_CONTENT, self._model, self._model_name),
        }

    def _get_repo(self, repo_id: str) -> Repository:
        """Look up a loaded repository or raise a sanitized HTTP error."""
        try:
            return self._repos[repo_id]
        except KeyError:
            raise WorkbenchError(404, "Repository not found") from None

    def health(self) -> Health:
        """Report the loaded model, repositories and uptime."""
        with self._lock:
            return Health("ok", self._model_name, list(self._repos), (perf_counter() - self._started) * 1000)

    def repos(self) -> list[RepoSummary]:
        """Return summaries of indexed repositories."""
        with self._lock:
            return [repo.summary for repo in self._repos.values()]

    def index_repo(self, request: IndexRequest) -> RepoSummary:
        """Register or rebuild an allowed local snapshot, publishing only complete builds."""
        try:
            root = validate_safe_local_path(request.path, self._allowed_roots)
        except ValueError:
            raise WorkbenchError(403, "Directory is outside allowed indexing roots or is unsafe") from None
        except (OSError, RuntimeError):
            raise WorkbenchError(422, "Index directory is unavailable") from None

        repo_id = request.repo_id or _generated_repo_id(root)
        if scan_and_redact_text(str(root))[1] or scan_and_redact_text(repo_id)[1]:
            raise WorkbenchError(403, "Index paths and IDs must be safe to display")
        with self._lock:
            previous = self._repos.get(repo_id)
            if previous is not None and root != previous.root:
                raise WorkbenchError(409, "Repository ID is already assigned to another path")
            default_content = previous.summary.content_types if previous is not None else _DEFAULT_CONTENT
            content = tuple(dict.fromkeys(request.content_types or default_content))
            if previous is not None and set(content) == set(default_content) and not request.force_rebuild:
                return previous.summary
            try:
                repo = _build_repo(repo_id, root, content, self._model, self._model_name)
            except (OSError, ValueError):
                raise WorkbenchError(422, "Could not index any supported source for this request") from None
            self._repos[repo_id] = repo
            return repo.summary

    def search(self, request: SearchRequest) -> dict[str, Any]:
        """Run a search and optionally compare with the original hybrid ranking in the same snapshot."""
        with self._lock:
            repo = self._get_repo(request.repo_id)
            primary = repo.search(request, request.mode)
            response = primary.to_dict()
            response["baseline_comparison"] = None
            if request.compare_baseline:
                baseline = primary if request.mode == "baseline" else repo.search(request, "baseline")
                response["baseline_comparison"] = baseline.to_dict() | {"rank_deltas": _rank_deltas(primary, baseline)}
            return response

    def files(self, repo_id: str) -> list[FileSummary]:
        """Return metadata for the indexed files in a repository."""
        with self._lock:
            return [file.summary for file in self._get_repo(repo_id).files.values()]

    def chunks(self, repo_id: str, path: str) -> FileChunks:
        """Return indexed AST spans with their redacted previews and safe token samples."""
        with self._lock:
            repo = self._get_repo(repo_id)
            file = repo.get_file(path)
            chunks = []
            for chunk in file.chunks:
                preview = repo.previews[chunk]
                tokens = tokenize_bilingual(enrich_for_bm25(replace(chunk, content=preview.content)))
                chunks.append(
                    IndexedChunk(
                        repo.chunk_ids[chunk],
                        chunk.start_line,
                        chunk.end_line,
                        preview.content,
                        estimate_tokens(preview.content),
                        tokens[:32],
                        preview.secrets_redacted,
                    )
                )
            return FileChunks(file.summary.file_path, file.summary.total_lines, chunks)

    def related(self, request: RelatedRequest) -> RelatedResponse:
        """Resolve a line to an indexed chunk and return similar code with safe previews."""
        with self._lock:
            repo = self._get_repo(request.repo_id)
            file = repo.get_file(request.file_path)
            seed = resolve_chunk(file.chunks, file.summary.file_path, request.line)
            if seed is None:
                raise WorkbenchError(404, "No indexed chunk contains this line")

            results = []
            for result in repo.index.find_related(seed, top_k=request.top_k):
                chunk = result.chunk
                preview = repo.previews[chunk]
                results.append(
                    RelatedResult(
                        repo.chunk_ids[chunk],
                        replace(chunk, content=preview.content),
                        result.score,
                        estimate_tokens(preview.content),
                        preview.secrets_redacted,
                    )
                )
            return RelatedResponse(request.repo_id, file.summary.file_path, request.line, results)

    def audit(self, repo_id: str | None = None) -> AuditResponse:
        """Report whole-file findings and aggregate counts with safe previews."""
        with self._lock:
            repos = self._repos if repo_id is None else {repo_id: self._get_repo(repo_id)}
            findings = [
                replace(finding, file_path=f"{label}/{finding.file_path}") if repo_id is None else finding
                for label, repo in repos.items()
                for file in repo.files.values()
                for finding in file.findings
            ]
            return AuditResponse(
                total_findings=len(findings),
                files_affected=len({row.file_path for row in findings}),
                by_rule=dict(Counter(row.rule for row in findings)),
                by_severity=dict(Counter(row.severity for row in findings)),
                findings=findings,
            )

    def benchmark(self) -> BenchmarkResponse:
        """Compare all modes on checked-in queries over both built-in repositories."""
        with self._lock:
            try:
                return run_benchmark(self._repos)
            except (KeyError, ValueError):
                raise WorkbenchError(409, "A benchmark source or relevance anchor is missing") from None

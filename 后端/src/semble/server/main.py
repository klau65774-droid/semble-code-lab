import json
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from semble.security import scan_and_redact_text
from semble.server.demo_repo import create_demo_repo
from semble.server.models import (
    AuditResponse,
    BenchmarkResponse,
    ErrorResponse,
    FileChunks,
    FilePath,
    FileSummary,
    Health,
    IndexRequest,
    RelatedRequest,
    RelatedResponse,
    RepoSummary,
    SearchRequest,
    SearchResponse,
)
from semble.server.service import Workbench, WorkbenchError


class _SafeAccessLog(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Keep Uvicorn's request query strings and recognized secrets out of logs."""
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            path = unquote(str(args[2]).partition("?")[0])
            path, _ = scan_and_redact_text(path)
            record.args = (*args[:2], path, *args[3:])
        return True


def _service(request: Request) -> Workbench:
    """Get the workbench initialized by the application lifespan."""
    return cast(Workbench, request.app.state.workbench)


router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> Health:
    """Report readiness and the currently loaded model and repositories."""
    return _service(request).health()


@router.get("/repos")
def repositories(request: Request) -> list[RepoSummary]:
    """List local repository snapshots."""
    return _service(request).repos()


@router.post("/repos/index", responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def index_repository(body: IndexRequest, request: Request) -> RepoSummary:
    """Index an allowed directory or rebuild a registered snapshot."""
    return _service(request).index_repo(body)


@router.post("/search", response_model=SearchResponse, responses={404: {"model": ErrorResponse}})
def search(body: SearchRequest, request: Request) -> dict[str, Any]:
    """Search with a score breakdown, redacted context, and optional rank comparison."""
    return _service(request).search(body)


@router.get("/repos/{repo_id}/files", responses={404: {"model": ErrorResponse}})
def files(repo_id: str, request: Request) -> list[FileSummary]:
    """List indexed files and their metadata."""
    return _service(request).files(repo_id)


@router.get("/repos/{repo_id}/chunks", responses={404: {"model": ErrorResponse}})
def chunks(repo_id: str, file_path: FilePath, request: Request) -> FileChunks:
    """Show redacted AST chunks and safe lexical token samples for one file."""
    return _service(request).chunks(repo_id, file_path)


@router.post("/chunks/related", responses={404: {"model": ErrorResponse}})
def related(body: RelatedRequest, request: Request) -> RelatedResponse:
    """Retrieve chunks near a selected source line in embedding space."""
    return _service(request).related(body)


@router.post("/benchmarks/run", responses={409: {"model": ErrorResponse}})
def benchmarks(request: Request) -> BenchmarkResponse:
    """Measure all retrieval modes against the built-in relevance annotations."""
    return _service(request).benchmark()


@router.get("/security/audit", responses={404: {"model": ErrorResponse}})
def audit(request: Request, repo_id: str | None = None) -> AuditResponse:
    """List sanitized credential findings from one or all indexed snapshots."""
    return _service(request).audit(repo_id)


async def _invalid_request(_request: Request, _error: Exception) -> JSONResponse:
    """Avoid echoing malformed input in validation responses."""
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


async def _workbench_error(_request: Request, error: Exception) -> JSONResponse:
    """Render an expected workbench error."""
    assert isinstance(error, WorkbenchError)
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


def create_app(*, allowed_roots: Sequence[Path] = ()) -> FastAPI:
    """Build the local API and start indexing when its lifespan begins."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        access_log = logging.getLogger("uvicorn.access")
        log_filter = _SafeAccessLog()
        access_log.addFilter(log_filter)
        try:
            with TemporaryDirectory(prefix="semble-workbench-") as temp_dir:
                demo_root = create_demo_repo(Path(temp_dir) / "bilingual-demo")
                application.state.workbench = Workbench(demo_root, allowed_roots)
                yield
        finally:
            access_log.removeFilter(log_filter)

    application = FastAPI(
        title="Semble Workbench",
        version="1.0.0",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse, "description": "Invalid request or source"}},
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.add_exception_handler(RequestValidationError, _invalid_request)
    application.add_exception_handler(WorkbenchError, _workbench_error)
    application.include_router(router)
    return application


app = create_app()


def export_openapi(path: Path) -> None:
    """Write the same OpenAPI schema served by the application, without indexing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export_openapi(Path("docs/openapi.json"))

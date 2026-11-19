import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from semble.server.main import create_app

_FAKE_KEY = "ghp_DemoFakeToken0000000000000000000000"
_DEMO = "/api/repos/bilingual-demo"
_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def approved(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Provide a writable root explicitly authorized for API registration."""
    return tmp_path_factory.mktemp("approved-index-roots")


@pytest.fixture(scope="module")
def client(local_model: Path, approved: Path) -> Iterator[TestClient]:
    """Exercise the real FastAPI lifespan and repository service with offline model files."""
    with pytest.MonkeyPatch.context() as environment:
        environment.setenv("SEMBLE_MODEL_NAME", str(local_model))
        environment.setenv("HF_HUB_OFFLINE", "1")
        environment.setenv("SEMBLE_CACHE_LOCATION", str(approved / "cache"))
        with TestClient(create_app(allowed_roots=[approved])) as test_client:
            yield test_client


def test_health_and_cors(client: TestClient) -> None:
    """Health exposes the two ready repositories and permits both local frontend origins."""
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["loaded_repos"] == ["semble-core", "bilingual-demo"]
    assert payload["model"]
    assert payload["uptime_ms"] > 0
    for host in ("127.0.0.1", "localhost"):
        origin = f"http://{host}:5173"
        preflight = client.options(
            "/api/search",
            headers={"origin": origin, "access-control-request-method": "POST"},
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin


def test_repositories(client: TestClient) -> None:
    """Default repo summaries describe the built-in 29-file core and multilingual fixture."""
    response = client.get("/api/repos")
    assert response.status_code == 200
    repos = {entry["repo_id"]: entry for entry in response.json()}
    assert repos["semble-core"]["indexed_files"] == 29
    assert repos["bilingual-demo"]["indexed_files"] == 11
    assert {"python", "typescript", "go", "sql"} <= set(repos["bilingual-demo"]["languages"])
    assert all(repo["total_chunks"] >= repo["indexed_files"] for repo in repos.values())
    assert all(repo["index_ms"] > 0 and repo["content_types"] for repo in repos.values())


def test_index_repo_builds_refreshes_and_keeps_last_successful_snapshot(client: TestClient, approved: Path) -> None:
    """Authorized registration and force rebuild publish coherent snapshots and exclude private paths."""
    root = approved / "project"
    root.mkdir()
    source = root / "main.py"
    source.write_text("def cache_key(): return 25\n", encoding="utf-8")
    private = root / ".ssh"
    private.mkdir()
    (private / "private.py").write_text("must_not_index = True", encoding="utf-8")
    (root / ".env.dev").write_text(f"TOKEN={_FAKE_KEY}", encoding="utf-8")

    request = {"repo_id": "local-project", "path": str(root)}
    first = client.post("/api/repos/index", json=request)
    assert first.status_code == 200
    assert first.json()["indexed_files"] == 1
    assert client.post("/api/repos/index", json=request).json() == first.json()

    (root / "other.py").write_text("def other(): return 502\n", encoding="utf-8")
    rebuilt = client.post("/api/repos/index", json={**request, "force_rebuild": True})
    assert rebuilt.status_code == 200
    assert rebuilt.json()["indexed_files"] == 2
    assert client.post("/api/repos/index", json={**request, "path": str(private)}).status_code == 403
    assert client.post("/api/repos/index", json={**request, "path": str(approved)}).status_code == 409
    assert client.post("/api/repos/index", json={"path": f"{root}/../project"}).status_code == 403
    failed = client.post("/api/repos/index", json={**request, "content_types": ["docs"]})
    assert failed.status_code == 422
    assert len(client.get("/api/repos/local-project/files").json()) == 2


def test_search_compares_real_rankings_and_returns_budgeted_context(client: TestClient) -> None:
    """A mixed query keeps top-K scores while the separately packed context respects its token ceiling."""
    response = client.post(
        "/api/search",
        json={
            "repo_id": "bilingual-demo",
            "query": "中文测试cache_key索引缓存路径",
            "token_budget": 200,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "enhanced"
    assert body["query_type"] == "embedded_symbol"
    assert body["detected_symbols"] == ["cache_key"]
    assert "缓存" in body["tokens"] and body["bm25_hits"] > 0
    assert body["alpha_used"] == 0.3
    assert 0 < body["packed_tokens"] <= 200
    assert body["packed_tokens"] == sum(chunk["estimated_tokens"] for chunk in body["packed_context"])
    comparison = body["baseline_comparison"]
    assert comparison["mode"] == "baseline"
    assert comparison["alpha_used"] == 0.5
    assert "缓存" not in comparison["tokens"]
    assert "baseline_rank" in comparison["rank_deltas"][0]
    for delta in comparison["rank_deltas"]:
        if delta["rank_delta"] is not None:
            assert delta["rank_delta"] == delta["baseline_rank"] - delta["primary_rank"]
    top = body["results"][0]
    assert top["chunk"]["file_path"].replace("\\", "/") == "services/cache.py"
    assert top["breakdown"]["final_score"] == top["score"]


def test_search_and_validation_do_not_return_original_credentials(client: TestClient) -> None:
    """Both rankings and both flag values mask fields that would otherwise carry the original secret."""
    for redact in (True, False):
        response = client.post(
            "/api/search",
            json={
                "repo_id": "bilingual-demo",
                "query": f"where is DEMO_GITHUB_TOKEN defined {_FAKE_KEY}",
                "redact_secrets": redact,
            },
        )
        assert response.status_code == 200
        assert _FAKE_KEY not in response.text
        assert any(row["secrets_redacted"] for row in response.json()["results"])
        assert _FAKE_KEY not in json.dumps(response.json()["baseline_comparison"], ensure_ascii=False)
    invalid = client.post("/api/search", json={"repo_id": "bilingual-demo", "query": "x", "top_k": _FAKE_KEY})
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "Invalid request"}
    assert _FAKE_KEY not in invalid.text


def test_search_language_filter_and_baseline_flag(client: TestClient) -> None:
    """Filtering applies to recalled definitions and an unrequested comparison stays empty."""
    response = client.post(
        "/api/search",
        json={
            "repo_id": "bilingual-demo",
            "query": "RequestRouter",
            "filter_languages": ["typescript"],
            "compare_baseline": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["baseline_comparison"] is None
    assert body["results"]
    assert {row["chunk"]["language"] for row in body["results"]} == {"typescript"}


def test_file_tree_exposes_index_metadata(client: TestClient) -> None:
    """The file tree includes token, ranking and security metadata without file bodies."""
    response = client.get(f"{_DEMO}/files")
    assert response.status_code == 200
    files = {row["file_path"].replace("\\", "/"): row for row in response.json()}
    assert files["tests/test_cache.py"]["path_penalty"] == 0.3
    creds = files["services/credential_demo.py"]
    assert creds["secrets_detected"] == 3
    assert creds["chunk_count"] > 0 and creds["estimated_tokens"] > 0 and creds["total_lines"] == 6
    assert "content" not in creds


def test_chunks_are_redacted_including_bm25_preview(client: TestClient) -> None:
    """File chunks keep AST spans and hide credentials from code and token previews."""
    response = client.get(f"{_DEMO}/chunks", params={"file_path": "services/credential_demo.py"})
    assert response.status_code == 200
    assert _FAKE_KEY not in response.text
    assert _FAKE_KEY.lower() not in response.text.lower()
    payload = response.json()
    assert payload["total_lines"] == 6
    assert sum(chunk["secrets_redacted"] for chunk in payload["chunks"]) == 3
    for chunk in payload["chunks"]:
        assert chunk["chunk_id"] and chunk["start_line"] <= chunk["end_line"]
        assert chunk["bm25_tokens_preview"]
    assert client.get(f"{_DEMO}/chunks", params={"file_path": "../services/cache.py"}).status_code == 404


def test_full_file_redaction_masks_a_pem_block_spanning_ast_chunks(client: TestClient, approved: Path) -> None:
    """Private key bodies are masked even where a returned chunk has neither PEM marker."""
    root = approved / "split-credential"
    root.mkdir()
    marker = "SYNTHETIC_ONLY_PEM_LINE_"
    body = "".join(f"# {marker}{i:02d}{'X' * 40}\n" for i in range(40))
    source = "# -----BEGIN PRIVATE KEY-----\n" + body + "# -----END PRIVATE KEY-----\n\nvalue = 25\n"
    (root / "sample.py").write_text(source, encoding="utf-8")
    indexed = client.post("/api/repos/index", json={"repo_id": "split-pem", "path": str(root)})
    assert indexed.status_code == 200
    assert indexed.json()["total_chunks"] >= 3
    chunks = client.get("/api/repos/split-pem/chunks", params={"file_path": "sample.py"})
    assert chunks.status_code == 200
    assert marker not in chunks.text
    assert marker.lower() not in chunks.text.lower()
    assert sum(row["secrets_redacted"] for row in chunks.json()["chunks"]) >= 3
    audit = client.get("/api/security/audit", params={"repo_id": "split-pem"}).json()
    assert audit["total_findings"] == 1
    assert audit["findings"][0]["line"] == 1


def test_related_chunks_are_safe_and_exclude_the_seed(client: TestClient) -> None:
    """Resolve a line to a source chunk and return nearby same-language snippets."""
    request = {"repo_id": "bilingual-demo", "file_path": "services/cache.py", "line": 8, "top_k": 3}
    response = client.post("/api/chunks/related", json=request)
    assert response.status_code == 200
    assert _FAKE_KEY not in response.text
    results = response.json()["results"]
    assert 0 < len(results) <= 3
    assert all(row["estimated_tokens"] > 0 for row in results)
    assert not any(
        row["chunk"]["file_path"].endswith("cache.py") and row["chunk"]["start_line"] <= 8 <= row["chunk"]["end_line"]
        for row in results
    )
    assert client.post("/api/chunks/related", json={**request, "line": 5000}).status_code == 404


def test_benchmark_returns_annotated_scores_for_four_modes(client: TestClient) -> None:
    """Compute the benchmark with both local repos and bounded, per-query metrics."""
    response = client.post("/api/benchmarks/run")
    assert response.status_code == 200
    body = response.json()
    assert body["query_count"] == len(body["queries"]) == 22
    assert {row["repo_id"] for row in body["queries"]} == {"semble-core", "bilingual-demo"}
    assert {"english", "embedded_symbol", "chinese", "mixed", "go", "typescript", "sql"} <= {
        row["category"] for row in body["queries"]
    }
    assert set(body["metrics"]) == {"enhanced", "baseline", "semantic", "bm25"}
    for mode, metrics in body["metrics"].items():
        assert metrics["p95_latency_ms"] > 0
        assert all(0 <= metrics[key] <= 1 for key in ("ndcg_at_10", "mrr_at_10", "recall_at_5"))
        assert all(row["modes"][mode]["latency_ms"] > 0 for row in body["queries"])
    assert all(row["relevant_chunk_ids"] for row in body["queries"])


def test_audit_exposes_only_redacted_findings(client: TestClient) -> None:
    """Repository audit groups findings by rule and reports masked metadata only."""
    response = client.get("/api/security/audit", params={"repo_id": "bilingual-demo"})
    assert response.status_code == 200
    assert _FAKE_KEY not in response.text
    body = response.json()
    assert body["files_affected"] == 1
    assert body["total_findings"] == 3
    assert body["by_rule"] == {"aws_access_key": 1, "aliyun_access_key": 1, "github_token": 1}
    assert [row["line"] for row in body["findings"]] == [4, 5, 6]
    for row in body["findings"]:
        assert set(row) == {"file_path", "line", "rule", "severity", "redacted_preview"}
        assert row["redacted_preview"].startswith("[REDACTED:")
    assert client.get("/api/security/audit").json()["total_findings"] >= 3


def test_openapi_snapshot_matches_all_nine_service_routes(client: TestClient) -> None:
    """Guard the generated OpenAPI contract against silent route or model drift."""
    schema = client.get("/openapi.json").json()
    expected = json.loads((_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert schema == expected
    assert len(schema["paths"]) == 9

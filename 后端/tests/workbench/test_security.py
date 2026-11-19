import logging
from pathlib import Path
from urllib.parse import quote

import pytest

from semble.security import scan_and_redact_text, validate_safe_local_path
from semble.server.main import _SafeAccessLog

_SYNTHETIC_SECRETS = [
    ("aws_access_key", "AKIAIOSFODNN7EXAMPLE"),
    ("aliyun_access_key", "LTAI5tDemoFakeKey0000"),
    ("github_token", "ghp_DemoFakeToken0000000000000000000000"),
    ("github_token", "github_pat_FAKE000000000000_fake_00000000000000"),
    ("openai_key", "sk-proj-FAKE_ONLY_DemoToken0000000000000000"),
    ("anthropic_key", "sk-ant-FAKE_ONLY_DemoToken0000000000000000"),
    ("slack_token", "xoxb-000000000000-synthetic-only"),
    ("pem_private_key", "-----BEGIN RSA PRIVATE KEY-----\nsynthetic-only\n-----END RSA PRIVATE KEY-----"),
    ("pem_private_key", "-----BEGIN OPENSSH PRIVATE KEY-----\ntruncated synthetic example"),
    ("jwt", "eyJzaWduYWwiOiJub25lIn0.eyJmYWtlIjp0cnVlfQ.fakeSignature"),
    ("bearer_token", "Bearer SyntheticOpaqueCredential000"),
    ("bearer_token", "Authorization: Bearer abcdefghijklmnop"),
    ("database_dsn", "postgres://workbench:fake-password@localhost:5432/demo"),
    ("database_dsn", "mysql://workbench:fake-password@localhost:3306/demo"),
    ("database_dsn", "redis://:fake-password@localhost:6379/0"),
    ("cn_mobile", "13800138000"),
    ("cn_mobile", "+86 13800138000"),
]


@pytest.mark.parametrize(("rule", "secret"), _SYNTHETIC_SECRETS, ids=[row[0] for row in _SYNTHETIC_SECRETS])
def test_secret_rules_remove_the_entire_synthetic_value(rule: str, secret: str) -> None:
    """Each rule emits safe evidence and preserves subsequent line numbers."""
    text = f"# [FAKE_TEST_ONLY]\n示例{secret}\n"
    redacted, findings = scan_and_redact_text(text)
    assert secret not in redacted
    assert redacted.count("\n") == text.count("\n")
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule == rule
    assert finding.line == 2
    assert finding.redacted_preview in redacted
    assert scan_and_redact_text(redacted) == (redacted, [])


@pytest.mark.parametrize(
    "ordinary",
    [
        "44238bc92a02f67c44bcb8e132b45cb36196d5d71eea6aeb5d8b63fda07991f36",
        "d41d8cd98f00b204e9800998ecf8427e",
        "123e4567-e89b-12d3-a456-426614174000",
        'model = "minishlab/potion-code-16M-v2"',
        "def load_model(model: str = 'model2vec', key: str | None = None):",
        "http://127.0.0.1:8000",
        "postgres://localhost:5432/demo",
        "redis://localhost:6379",
        "version = '1.13800138000.2'",
        "time_ns = 1738001380000",
        "attempt = 429",
        "ref = 1231380013800099",
        "the client uses Bearer authentication",
        "ticket = 'PRJ-13800138000-2'",
    ],
)
def test_code_and_metadata_are_not_false_positives(ordinary: str) -> None:
    """Known benign code, hashes, model names and version/number formats stay untouched."""
    assert scan_and_redact_text(ordinary) == (ordinary, [])


def test_path_whitelist_checks_existing_and_sensitive_paths(tmp_path: Path) -> None:
    """Allow listed nested directories and reject siblings, traversal and private paths."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    private = allowed / ".ssh"
    private.mkdir()
    sibling = tmp_path / "allowed-suffix"
    sibling.mkdir()
    assert validate_safe_local_path(str(allowed), [allowed]) == allowed.resolve()
    invalid = [str(private), str(sibling), f"{allowed}/../allowed", "\\\\server\\share", "C:\\Windows", "C:relative"]
    for path in invalid:
        with pytest.raises(ValueError):
            validate_safe_local_path(path, [allowed])


def test_resolved_symlink_target_must_stay_in_allowed_root(tmp_path: Path) -> None:
    """The whitelist is enforced on the canonical target of a link."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "not-allowed"
    outside.mkdir()
    link = allowed / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        validate_safe_local_path(str(link), [allowed])


def test_request_log_excludes_secrets_in_paths_and_query_strings() -> None:
    """Uvicorn logs keep a sanitized request target, including with URL-encoded tokens."""
    secret = "ghp_DemoFakeToken0000000000000000000000"
    encoded = f"%67{quote(secret[1:])}"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "uvicorn",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", f"/api/repos/{encoded}?file_path={secret}", "1.1", 404),
        None,
    )
    assert _SafeAccessLog().filter(record)
    assert secret not in record.getMessage()
    assert "file_path" not in record.getMessage()
    assert "[REDACTED:github_token]" in record.getMessage()

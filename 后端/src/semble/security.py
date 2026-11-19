import os
import re
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from semble.tokens import ASCII_LEFT_BOUNDARY, ASCII_RIGHT_BOUNDARY

_PEM_BOUNDARY = re.compile(r"-----(BEGIN|END) ((?:[A-Z0-9]+ )*PRIVATE KEY)-----")
_INLINE_SECRET = re.compile(
    rf"{ASCII_LEFT_BOUNDARY}(?:"
    r"(?P<aws_access_key>AKIA[A-Z0-9]{16})"
    r"|(?P<aliyun_access_key>LTAI[A-Za-z0-9]{16,24})"
    r"|(?P<github_token>ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"
    r"|(?P<anthropic_key>sk-ant-[A-Za-z0-9_-]{16,})"
    r"|(?P<openai_key>sk-[A-Za-z0-9_-]{16,})"
    r"|(?P<slack_token>xox[baprs]-[A-Za-z0-9-]{10,})"
    r"""|(?P<bearer_token>(?i:authorization)[ \t]*[:=][ \t]*["']?(?i:bearer)[ \t]+[A-Za-z0-9._~+/-]{4,}={0,2}"""
    r"|(?i:Bearer)[ \t]+(?:"
    r"(?=[A-Za-z0-9._~+/-]*[0-9._~+/-])[A-Za-z0-9._~+/-]{12,}|[A-Za-z]{20,})={0,2})"
    r"|(?P<jwt>eyJ[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,})"
    r"|(?P<database_dsn>(?i:postgres(?:ql)?|mysql|rediss?)://"
    r"""[^\s:@/"'<>]*:[^\s@"'<>]+@[^\s/"'<>),;]+(?:/[^\s"'<>),;]*)?)"""
    r"|(?P<cn_mobile>(?<![+.\-])(?:\+?86[ -]?)?1[3-9][0-9]{9}(?![.\-][0-9]))"
    rf"){ASCII_RIGHT_BOUNDARY}"
)

_SENSITIVE_DIRS = frozenset(
    {".ssh", ".aws", ".azure", ".gnupg", ".git", ".kube", "system volume information", "$recycle.bin"}
)
_SYSTEM_ROOTS = frozenset({"windows", "etc", "proc", "sys", "dev"})
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    line: int
    rule: str
    severity: str
    redacted_preview: str
    start: int
    end: int


def _pem_spans(text: str) -> Iterator[tuple[int, int]]:
    """Yield private key ranges, closing a truncated block at the end of the source."""
    opening: re.Match[str] | None = None
    for marker in _PEM_BOUNDARY.finditer(text):
        if opening is None and marker.group(1) == "BEGIN":
            opening = marker
        elif opening is not None and marker.group(1) == "END" and marker.group(2) == opening.group(2):
            yield opening.start(), marker.end()
            opening = None
    if opening is not None:
        yield opening.start(), len(text)


def _inline_spans(text: str, start: int, end: int) -> Iterator[tuple[int, int, str]]:
    """Find inline credentials in the requested source range."""
    for match in _INLINE_SECRET.finditer(text, start, end):
        assert match.lastgroup is not None
        yield match.start(), match.end(), match.lastgroup


def _secret_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Find non-overlapping credentials, giving a private key block precedence over its contents."""
    cursor = 0
    for start, end in _pem_spans(text):
        yield from _inline_spans(text, cursor, start)
        yield start, end, "pem_private_key"
        cursor = end
    yield from _inline_spans(text, cursor, len(text))


def redact_range(text: str, findings: Sequence[SecretFinding], start: int, end: int) -> tuple[str, int]:
    """Redact all secret spans intersecting the requested range and preserve its line numbers."""
    parts: list[str] = []
    cursor = start
    count = 0
    for finding in findings:
        if finding.end <= cursor:
            continue
        if finding.start >= end:
            break
        masked_start, masked_end = max(start, finding.start), min(end, finding.end)
        line_breaks = "\n" * text.count("\n", masked_start, masked_end)
        parts.extend((text[cursor:masked_start], finding.redacted_preview, line_breaks))
        cursor = masked_end
        count += 1
    if not count:
        return text[start:end], 0
    parts.append(text[cursor:end])
    return "".join(parts), count


def scan_and_redact_text(text: str) -> tuple[str, list[SecretFinding]]:
    """Return a redacted copy and rule/line evidence with no original credential values."""
    findings = []
    cursor = 0
    line = 1
    for start, end, rule in _secret_spans(text):
        line += text.count("\n", cursor, start)
        cursor = start
        severity = "medium" if rule == "cn_mobile" else "high"
        findings.append(SecretFinding(line, rule, severity, f"[REDACTED:{rule}]", start, end))
    if not findings:
        return text, findings
    redacted, _ = redact_range(text, findings, 0, len(text))
    return redacted, findings


def _has_sensitive_component(path: PureWindowsPath) -> bool:
    """Check private directory names and system-level directories."""
    parts = [part.rstrip(" .").casefold() for part in path.parts if part != path.anchor]
    return (bool(path.root and parts) and parts[0] in _SYSTEM_ROOTS) or any(
        part in _SENSITIVE_DIRS or part == ".env" or part.startswith(".env.") for part in parts
    )


def _has_unsafe_syntax(path: str, windows_path: PureWindowsPath) -> bool:
    """Reject traversal, network/device paths, and drive-relative or alternate-stream syntax."""
    return (
        not path.strip()
        or "\x00" in path
        or path.replace("\\", "/").startswith("//")
        or bool(windows_path.drive and (os.name != "nt" or not windows_path.root))
        or any(part.rstrip(" ") == ".." or ":" in part for part in windows_path.parts if part != windows_path.anchor)
    )


def validate_safe_local_path(path: str, allowed_roots: Sequence[Path]) -> Path:
    """Resolve an existing directory and require containment in an allowed local root."""
    windows_path = PureWindowsPath(path)
    if _has_unsafe_syntax(path, windows_path) or _has_sensitive_component(windows_path):
        raise ValueError("Unsafe local path")
    resolved = Path(path).resolve(strict=True)
    if _has_sensitive_component(PureWindowsPath(resolved)) or not any(
        resolved.is_relative_to(root.resolve()) for root in allowed_roots
    ):
        raise ValueError("Directory is outside allowed indexing roots")
    if not resolved.is_dir():
        raise NotADirectoryError("An index root must be a directory")
    return resolved


def is_safe_index_entry(path: Path) -> bool:
    """Screen individual files and directories before opening or descending into them."""
    if _has_sensitive_component(PureWindowsPath(path)):
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    return not (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)

import functools
import re
from collections.abc import Callable
from pathlib import Path

from semble.tokens import (
    ASCII_IDENTIFIER,
    ASCII_LEFT_BOUNDARY,
    ASCII_RIGHT_BOUNDARY,
    cjk_ratio,
    expand_cjk_concepts,
    split_identifier,
    tokenize_bilingual,
)
from semble.types import Chunk

# Symbol-lookup queries: namespace-qualified, leading-underscore, or containing
# uppercase/underscore. Plain lowercase words (e.g. "session") are NL, not symbols.
_SYMBOL_QUERY_RE = re.compile(
    r"^(?:"
    r"[A-Za-z_][A-Za-z0-9_]*(?:(?:::|\\|->|\.)[A-Za-z_][A-Za-z0-9_]*)+"  # namespace-qualified
    r"|_[A-Za-z0-9_]*"  # leading underscore
    r"|[A-Za-z][A-Za-z0-9]*[A-Z_][A-Za-z0-9_]*"  # contains uppercase or underscore
    r"|[A-Z][A-Za-z0-9]*"  # starts with uppercase
    r")$"
)

# CamelCase/camelCase identifiers embedded in a NL query; excludes plain words and pure acronyms.
_EMBEDDED_SYMBOL_RE = re.compile(
    r"\b(?:"
    r"[A-Z][a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*"  # PascalCase
    r"|[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+"  # camelCase
    r")\b"
)

_ENHANCED_EMBEDDED_SYMBOL_RE = re.compile(
    rf"{ASCII_LEFT_BOUNDARY}(?:"
    rf"{ASCII_IDENTIFIER}(?:(?:::|\.){ASCII_IDENTIFIER})+"
    r"|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]*|_+[A-Za-z][A-Za-z0-9_]*"
    r"|[A-Z](?:[A-Z0-9]*[A-Z][a-z]|[a-z0-9]+[A-Z])[a-zA-Z0-9]*"
    r"|[a-z][a-z0-9]*[A-Z][a-zA-Z0-9]*"
    rf"){ASCII_RIGHT_BOUNDARY}"
)

# Minimum stem length for prefix-based non-candidate scan (avoids over-broad matches).
_EMBEDDED_STEM_MIN_LEN = 4

# Half-strength: the symbol may be incidental to the NL query.
_EMBEDDED_SYMBOL_BOOST_SCALE = 0.5

# Case-sensitive: IGNORECASE produces false positives like "Module" in Python docs
# or "Class" method calls in Ruby.
_DEFINITION_KEYWORDS = (
    "class",
    "module",
    "defmodule",  # Elixir
    "def",
    "interface",
    "struct",
    "enum",
    "trait",
    "type",
    "func",
    "function",
    "object",
    "abstract class",
    "data class",
    "fn",
    "fun",  # Kotlin
    "package",
    "namespace",
    "protocol",  # Swift
    "record",  # C# 9+, Java 16+
    "typedef",  # C/C++/Dart
)

# SQL DDL is conventionally all-caps or all-lowercase; match both via IGNORECASE.
_SQL_DEFINITION_KEYWORDS = (
    "CREATE TABLE",
    "CREATE VIEW",
    "CREATE PROCEDURE",
    "CREATE FUNCTION",
)

_KEYWORD_PREFIX = r"(?:^|(?<=\s))(?:"
_DEFINITION_KEYWORD_BODY = "|".join(re.escape(keyword) for keyword in _DEFINITION_KEYWORDS)
_SQL_KEYWORD_BODY = "|".join(re.escape(keyword) for keyword in _SQL_DEFINITION_KEYWORDS)

# Additive boost multiplier for chunks that define a queried symbol.
_DEFINITION_BOOST_MULTIPLIER = 3.0

# Additive boost multiplier for NL queries when file stems match query words.
_STEM_BOOST_MULTIPLIER = 1.0

# Fraction of max_score added to each file's top chunk, scaled by its aggregate candidate score.
_FILE_COHERENCE_BOOST_FRAC = 0.2

_ALPHA_CJK = 0.20  # favor bilingual/expanded BM25 when query has CJK without ASCII terms
_ALPHA_SYMBOL = 0.3  # lean BM25 for exact keyword matching
_ALPHA_MIXED_CJK = 0.30  # balance bilingual BM25 and dense vectors for CN+EN queries
_ALPHA_EMBEDDED = 0.4
_ALPHA_NL = 0.5  # balanced semantic + BM25

# Common English stopwords excluded from file-stem matching for NL queries.
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how if in is it not of on or the to was"
    " what when where which who why with".split()
)


def apply_query_boost(
    combined_scores: dict[Chunk, float],
    query: str,
    all_chunks: list[Chunk],
    *,
    enhanced: bool = False,
    reasons: dict[Chunk, list[str]] | None = None,
) -> dict[Chunk, float]:
    """Apply query-type boosts to candidate scores."""
    if not combined_scores:
        return combined_scores

    max_score = max(combined_scores.values())
    boosted = dict(combined_scores)

    if enhanced:
        symbols = detect_symbols(query, enhanced=True)
        bare_symbol = is_symbol_query(query)
        if not bare_symbol:
            _boost_stem_matches(boosted, query, max_score, enhanced=True, reasons=reasons)
        _boost_enhanced_definitions(boosted, symbols, all_chunks, max_score, bare_symbol, reasons)
        return boosted

    if is_symbol_query(query):
        _boost_symbol_definitions(boosted, query, max_score, all_chunks, reasons)
    else:
        _boost_stem_matches(boosted, query, max_score, reasons=reasons)
        _boost_embedded_symbols(boosted, query, max_score, all_chunks, reasons)

    return boosted


def boost_multi_chunk_files(scores: dict[Chunk, float]) -> None:
    """Promote files with multiple high-scoring chunks by boosting their top chunk (in-place)."""
    if not scores:
        return

    max_score = max(scores.values())
    if max_score == 0.0:
        return

    file_sum: dict[str, float] = {}
    best_chunk: dict[str, Chunk] = {}
    for chunk, score in scores.items():
        file_path = chunk.file_path
        file_sum[file_path] = file_sum.get(file_path, 0.0) + score
        if file_path not in best_chunk or score > scores[best_chunk[file_path]]:
            best_chunk[file_path] = chunk

    max_file_sum = max(file_sum.values())
    boost_unit = max_score * _FILE_COHERENCE_BOOST_FRAC
    for file_path, chunk in best_chunk.items():
        scores[chunk] += boost_unit * file_sum[file_path] / max_file_sum


def is_symbol_query(query: str) -> bool:
    """Return True if the query looks like a bare symbol or namespace-qualified identifier."""
    return _SYMBOL_QUERY_RE.match(query.strip()) is not None


def detect_symbols(query: str, *, enhanced: bool = False) -> list[str]:
    """Return unique query symbols in order of appearance."""
    if is_symbol_query(query):
        return [query.strip()]
    pattern = _ENHANCED_EMBEDDED_SYMBOL_RE if enhanced else _EMBEDDED_SYMBOL_RE
    return list(dict.fromkeys(pattern.findall(query)))


def resolve_alpha(query: str, alpha: float | None, *, enhanced: bool = False) -> float:
    """Return the blending weight for semantic scores, auto-detecting from query type."""
    if alpha is not None:
        return alpha
    if is_symbol_query(query):
        return _ALPHA_SYMBOL
    if enhanced:
        if cjk_ratio(query) > 0.0:
            has_ascii_letters = any("a" <= ch <= "z" or "A" <= ch <= "Z" for ch in query)
            return _ALPHA_MIXED_CJK if has_ascii_letters else _ALPHA_CJK
        if _ENHANCED_EMBEDDED_SYMBOL_RE.search(query):
            return _ALPHA_EMBEDDED
    return _ALPHA_NL


def _extract_symbol_name(query: str) -> str:
    """Extract the final identifier from a possibly namespace-qualified query.

    Examples: "Sinatra::Base" → "Base", "Client" → "Client".
    """
    for separator in ("::", "\\", "->", "."):
        if separator in query:
            return query.rsplit(separator, 1)[-1]
    return query.strip()


@functools.lru_cache(maxsize=256)
def _definition_pattern(symbol_name: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    escaped = re.escape(symbol_name)
    ns_prefix = r"(?:[A-Za-z_][A-Za-z0-9_]*(?:\.|::))*"
    suffix = r")\s+" + ns_prefix + escaped + r"(?:\s|[<({:\[;]|$)"
    return (
        re.compile(_KEYWORD_PREFIX + _DEFINITION_KEYWORD_BODY + suffix, re.MULTILINE),
        re.compile(_KEYWORD_PREFIX + _SQL_KEYWORD_BODY + suffix, re.MULTILINE | re.IGNORECASE),
    )


def _chunk_defines_symbol(chunk: Chunk, symbol_name: str) -> bool:
    """Return True if the chunk contains a definition of *symbol_name*.

    Case-sensitive for general keywords, case-insensitive for SQL DDL.
    Also matches namespace-qualified forms (e.g. ``defmodule Phoenix.Router`` for ``Router``).
    """
    general, sql = _definition_pattern(symbol_name)
    return general.search(chunk.content) is not None or sql.search(chunk.content) is not None


def _stem_matches(stem: str, name: str) -> bool:
    """Return True if *stem* matches *name* (exact, snake_case-normalised, or plural)."""
    stem_norm = stem.replace("_", "")
    return stem == name or stem_norm == name or stem.rstrip("s") == name or stem_norm.rstrip("s") == name


@functools.lru_cache(maxsize=4096)
def _file_stem(file_path: str) -> str:
    """Return the lowercased file stem, cached because definition boosting checks it for every chunk."""
    return Path(file_path).stem.lower()


def _definition_tier(chunk: Chunk, names: set[str], boost_unit: float) -> float:
    """Return the boost amount for a chunk that defines one of *names* (0.0 if none match)."""
    if not any(_chunk_defines_symbol(chunk, name) for name in names):
        return 0.0
    stem = _file_stem(chunk.file_path)
    return boost_unit * (1.5 if any(_stem_matches(stem, name.lower()) for name in names) else 1.0)


def _add_boost(
    boosted: dict[Chunk, float],
    chunk: Chunk,
    amount: float,
    reason: str,
    reasons: dict[Chunk, list[str]] | None,
) -> None:
    """Add a score contribution and record its origin when requested."""
    boosted[chunk] = boosted.get(chunk, 0.0) + amount
    if reasons is not None:
        reasons.setdefault(chunk, []).append(reason)


def _boost_definitions(
    boosted: dict[Chunk, float],
    names: set[str],
    boost_unit: float,
    all_chunks: list[Chunk],
    stem_ok: Callable[[str], bool],
    reason: str,
    reasons: dict[Chunk, list[str]] | None,
) -> None:
    """Boost candidates defining one of names, then add non-candidates whose lowercased file stem satisfies stem_ok."""
    for chunk in list(boosted):
        if tier := _definition_tier(chunk, names, boost_unit):
            _add_boost(boosted, chunk, tier, reason, reasons)
    for chunk in all_chunks:
        if not stem_ok(_file_stem(chunk.file_path)) or chunk in boosted:
            continue
        if tier := _definition_tier(chunk, names, boost_unit):
            _add_boost(boosted, chunk, tier, reason, reasons)


def _boost_symbol_definitions(
    boosted: dict[Chunk, float],
    query: str,
    max_score: float,
    all_chunks: list[Chunk],
    reasons: dict[Chunk, list[str]] | None,
) -> None:
    """Boost chunks that define the queried symbol, scanning candidates and stem-matched non-candidates (in-place)."""
    symbol_name = _extract_symbol_name(query)
    names = {symbol_name}
    if symbol_name != query.strip():
        names.add(query.strip())

    boost_unit = max_score * _DEFINITION_BOOST_MULTIPLIER
    _boost_definitions(
        boosted,
        names,
        boost_unit,
        all_chunks,
        lambda stem: _stem_matches(stem, symbol_name.lower()),
        "symbol_definition",
        reasons,
    )


def _boost_embedded_symbols(
    boosted: dict[Chunk, float],
    query: str,
    max_score: float,
    all_chunks: list[Chunk],
    reasons: dict[Chunk, list[str]] | None,
) -> None:
    """Boost chunks defining CamelCase/camelCase symbols embedded in NL queries (in-place).

    Half-strength vs pure symbol queries. Non-candidate scan uses stem-prefix match
    so e.g. ``state.ts`` is found for symbol ``StateManager``.
    """
    names = set(_EMBEDDED_SYMBOL_RE.findall(query))
    if not names:
        return

    boost_unit = max_score * _DEFINITION_BOOST_MULTIPLIER * _EMBEDDED_SYMBOL_BOOST_SCALE
    symbols_lower = frozenset(s.lower() for s in names)

    def stem_ok(stem: str) -> bool:
        stem_norm = stem.replace("_", "")
        return any(
            stem == symbol_lower
            or stem_norm == symbol_lower
            or (len(stem) >= _EMBEDDED_STEM_MIN_LEN and symbol_lower.startswith(stem))
            or (len(stem_norm) >= _EMBEDDED_STEM_MIN_LEN and symbol_lower.startswith(stem_norm))
            for symbol_lower in symbols_lower
        )

    _boost_definitions(boosted, names, boost_unit, all_chunks, stem_ok, "embedded_symbol_definition", reasons)


@functools.lru_cache(maxsize=256)
def _binding_pattern(name: str) -> re.Pattern[str]:
    """Match explicit declarations at any indent or bare module-level bindings at column 0."""
    return re.compile(
        rf"(?m)(?:^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+|^){re.escape(name)}"
        rf"{ASCII_RIGHT_BOUNDARY}(?:[ \t]*:[^=\n]+)?[ \t]*:?=(?!=)"
    )


@functools.lru_cache(maxsize=256)
def _method_pattern(name: str) -> re.Pattern[str]:
    """Match Go receiver methods and JavaScript/TypeScript method bodies or declarations."""
    name = re.escape(name)
    return re.compile(
        rf"(?m)^[ \t]*(?:func[ \t]+\([^)\n]+\)[ \t]+{name}[ \t]*\("
        rf"|(?:(?:public|protected|private|static|async|override|abstract)[ \t]+)+{name}[ \t]*\("
        rf"|{name}[ \t]*\([^)\n]*\)[ \t]*(?::[^{{\n]+)?\{{)"
    )


def _enhanced_defines_symbol(chunk: Chunk, name: str) -> bool:
    """Check definitions after a cheap substring test, including case-insensitive SQL."""
    if name in chunk.content:
        return (
            _chunk_defines_symbol(chunk, name)
            or _binding_pattern(name).search(chunk.content) is not None
            or (
                chunk.language in ("go", "typescript", "tsx", "javascript", "jsx")
                and _method_pattern(name).search(chunk.content) is not None
            )
        )
    return (
        chunk.language == "sql"
        and name.lower() in chunk.content.lower()
        and _definition_pattern(name)[1].search(chunk.content) is not None
    )


def _boost_enhanced_definitions(
    boosted: dict[Chunk, float],
    symbols: list[str],
    all_chunks: list[Chunk],
    max_score: float,
    bare_symbol: bool,
    reasons: dict[Chunk, list[str]] | None,
) -> None:
    """Recall actual definitions even when their filenames and retrieval ranks do not match."""
    if not symbols:
        return
    names = list(dict.fromkeys(name for symbol in symbols for name in (_extract_symbol_name(symbol), symbol)))
    scale = 1.0 if bare_symbol else _EMBEDDED_SYMBOL_BOOST_SCALE
    boost_unit = max_score * _DEFINITION_BOOST_MULTIPLIER * scale
    reason = "symbol_definition" if bare_symbol else "embedded_symbol_definition"
    for chunk in all_chunks:
        matches = [name for name in names if _enhanced_defines_symbol(chunk, name)]
        if matches:
            stem = _file_stem(chunk.file_path)
            multiplier = 1.5 if any(_stem_matches(stem, name.lower()) for name in matches) else 1.0
            _add_boost(boosted, chunk, boost_unit * multiplier, reason, reasons)


def _count_keyword_matches(keywords: set[str], parts: set[str]) -> int:
    """Count query keywords that match path parts, allowing prefix overlap (min 3 chars)."""
    exact = keywords & parts
    n_matches = len(exact)
    for keyword in keywords - exact:
        for part in parts:
            shorter, longer = (keyword, part) if len(keyword) <= len(part) else (part, keyword)
            if len(shorter) >= 3 and longer.startswith(shorter):
                n_matches += 1
                break
    return n_matches


def _boost_stem_matches(
    boosted: dict[Chunk, float],
    query: str,
    max_score: float,
    *,
    enhanced: bool = False,
    reasons: dict[Chunk, list[str]] | None = None,
) -> None:
    """Boost chunks whose file paths match NL query keywords (in-place).

    Uses prefix matching for morphological variants (e.g. "dependency" matches
    "dependencies").  Matches file stems and the immediate parent directory name.
    """
    words = (
        tokenize_bilingual(query) + expand_cjk_concepts(query)
        if enhanced
        else [word.lower() for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query)]
    )
    keywords = {word for word in words if len(word) >= (3 if word.isascii() else 2) and word not in _STOPWORDS}
    if not keywords:
        return

    boost = max_score * _STEM_BOOST_MULTIPLIER
    path_cache: dict[str, set[str]] = {}
    for chunk in list(boosted):
        if chunk.file_path not in path_cache:
            path = Path(chunk.file_path)
            split = tokenize_bilingual if enhanced else split_identifier
            parts = set(split(path.stem))
            if path.parent.name and path.parent.name not in (".", "/", ".."):
                parts.update(split(path.parent.name))
            path_cache[chunk.file_path] = parts
        n_matches = _count_keyword_matches(keywords, path_cache[chunk.file_path])
        if n_matches > 0:
            match_ratio = n_matches / len(keywords)
            if match_ratio >= 0.10:
                _add_boost(boosted, chunk, boost * match_ratio, "file_stem_match", reasons)

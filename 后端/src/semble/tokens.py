import re

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
ASCII_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
ASCII_LEFT_BOUNDARY = r"(?<![A-Za-z0-9_])"
ASCII_RIGHT_BOUNDARY = r"(?![A-Za-z0-9_])"
CJK_CHARACTERS = r"[\u4e00-\u9fff]"
_BILINGUAL_TOKEN_RE = re.compile(
    rf"{ASCII_LEFT_BOUNDARY}(?:{ASCII_IDENTIFIER}|[1-9][0-9]{{2,3}}){ASCII_RIGHT_BOUNDARY}|{CJK_CHARACTERS}+"
)
_CJK_CHAR_RE = re.compile(CJK_CHARACTERS)
_ALNUM_OR_CJK_RE = re.compile(rf"[A-Za-z0-9]|{CJK_CHARACTERS}")
_CJK_SPAN_RE = re.compile(rf"{CJK_CHARACTERS}+")
_NUMERIC_CODE_RE = re.compile(rf"{ASCII_LEFT_BOUNDARY}[1-9][0-9]{{2,3}}{ASCII_RIGHT_BOUNDARY}")
_CJK_STOP_WORD_RE = re.compile(r"如何|怎么|哪里|[的了和与在是]")

_CN_SE_CONCEPT_MAP: dict[str, tuple[str, ...]] = {
    "重排序": ("rerank",),
    "扩展名": ("extension", "extensions"),
    "序列化": ("serialize", "serialization", "encoder", "encoders"),
    "中间件": ("middleware",),
    "客户端": ("client",),
    "持久化": ("persist", "save"),
    "数据库": ("database", "sql"),
    "混合": ("hybrid",),
    "检索": ("search", "retrieval"),
    "搜索": ("search",),
    "重排": ("rerank",),
    "打分": ("score", "scoring"),
    "评分": ("score",),
    "融合": ("fusion", "rrf"),
    "合并": ("merge",),
    "缓存": ("cache",),
    "索引": ("index",),
    "增量": ("incremental",),
    "分词": ("tokenize", "tokens"),
    "向量": ("vector", "embedding"),
    "语义": ("semantic",),
    "符号": ("symbol",),
    "定义": ("def", "define"),
    "惩罚": ("penalty", "penalise"),
    "降权": ("penalty", "decay"),
    "衰减": ("decay",),
    "路径": ("path",),
    "路由": ("route", "router", "routing"),
    "鉴权": ("auth", "security"),
    "认证": ("auth", "authentication", "oauth2", "security"),
    "安全": ("security",),
    "限流": ("ratelimit", "limiter"),
    "频率": ("rate", "limit"),
    "重试": ("retry",),
    "退避": ("backoff", "delay"),
    "超时": ("timeout",),
    "并发": ("concurrency", "async"),
    "异步": ("async", "concurrency"),
    "同步": ("sync",),
    "阻塞": ("blocking", "block"),
    "脱敏": ("redact", "secret"),
    "凭据": ("credential", "secret"),
    "密钥": ("secret", "key"),
    "依赖": ("dependency", "dependencies"),
    "注入": ("injection", "dependencies"),
    "异常": ("exception", "exceptions", "error"),
    "错误": ("error", "exception"),
    "校验": ("validate", "validation"),
    "验证": ("validate", "validation"),
    "编码": ("encode", "encoder"),
    "分块": ("chunk", "chunking"),
    "切分": ("split", "chunk"),
    "解析": ("parse", "parser"),
    "跨域": ("cors",),
    "后台": ("background",),
    "任务": ("task", "background"),
    "上传": ("upload", "uploads"),
    "文件": ("file", "files"),
    "语言": ("language",),
    "配置": ("config", "configuration"),
    "查询": ("query",),
    "租户": ("tenant",),
    "过期": ("expire", "ttl"),
    "清理": ("delete", "cleanup"),
    "日志": ("log", "logging"),
    "测试": ("test",),
    "网关": ("gateway",),
    "响应": ("response",),
    "请求": ("request",),
    "互斥": ("mutex",),
    "锁": ("lock", "mutex"),
    "窗口": ("window",),
    "计数": ("counter",),
    "去重": ("dedup",),
    "重复": ("repeat", "duplicate"),
    "过滤": ("filter",),
    "排序": ("sort", "rank"),
    "接口": ("endpoint", "interface"),
    "端点": ("endpoint",),
    "令牌": ("token", "oauth2"),
    "模型": ("model",),
    "连接": ("connection",),
    "会话": ("session",),
    "失效": ("invalidate",),
    "回退": ("fallback",),
    "模式": ("schema",),
    "架构": ("architecture",),
    "插件": ("plugin",),
    "队列": ("queue",),
    "代理": ("proxy",),
    "权限": ("permission",),
    "嵌套": ("nested",),
    "生成": ("generate", "generation"),
    "注册": ("register", "registered"),
}
_SORTED_CN_CONCEPT_KEYS = tuple(sorted(_CN_SE_CONCEPT_MAP, key=len, reverse=True))

# Split on camelCase/PascalCase boundaries:
#   "HandlerStack" -> ["Handler", "Stack"]
#   "getHTTPResponse" -> ["get", "HTTP", "Response"]
#   "XMLParser" -> ["XML", "Parser"]
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def split_identifier(token: str) -> list[str]:
    """Split a single identifier into sub-tokens via camelCase/snake_case.

    Returns the original token (lowered) plus any sub-tokens.
    E.g. "HandlerStack" -> ["handlerstack", "handler", "stack"]
         "my_func" -> ["my_func", "my", "func"]
         "simple" -> ["simple"]
    """
    lower = token.lower()
    parts: list[str] = []

    if "_" in token:
        # snake_case splitting
        parts = [p for p in lower.split("_") if p]
    else:
        # camelCase / PascalCase splitting
        parts = [m.lower() for m in _CAMEL_RE.findall(token)]

    if len(parts) >= 2:
        return [lower, *parts]
    return [lower]


def tokenize(text: str, *, multilingual: bool = False) -> list[str]:
    """Split text into lowercase identifier-like tokens for BM25 indexing.

    Compound identifiers (camelCase, PascalCase, snake_case) are expanded
    into sub-tokens so that partial matches work. The original compound
    token is preserved for exact-match boosting.
    """
    if multilingual:
        return tokenize_bilingual(text)
    result: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        result.extend(split_identifier(tok))
    return result


def tokenize_bilingual(text: str) -> list[str]:
    """Expand code identifiers and emit 3-4 digit numeric codes and CJK unigrams/bigrams in text order."""
    result: list[str] = []
    for token in _BILINGUAL_TOKEN_RE.findall(text):
        if token.isascii():
            result.extend(split_identifier(token))
            continue
        for run in _CJK_STOP_WORD_RE.split(token):
            result.extend(run)
            result.extend(run[index : index + 2] for index in range(len(run) - 1))
    return result


def cjk_ratio(text: str) -> float:
    """Return the fraction of alphanumeric or CJK characters in text that are CJK."""
    cjk_count = len(_CJK_CHAR_RE.findall(text))
    if cjk_count == 0:
        return 0.0
    total = len(_ALNUM_OR_CJK_RE.findall(text))
    return cjk_count / total if total else 0.0


def expand_cjk_concepts(text: str) -> list[str]:
    """Expand Chinese software-engineering terms in a query into universal English keywords."""
    expanded: list[str] = []
    seen: set[str] = set()
    for span in _CJK_SPAN_RE.findall(text):
        pos = 0
        span_len = len(span)
        while pos < span_len:
            matched = False
            for key in _SORTED_CN_CONCEPT_KEYS:
                if span.startswith(key, pos):
                    for term in _CN_SE_CONCEPT_MAP[key]:
                        if term not in seen:
                            seen.add(term)
                            expanded.append(term)
                    pos += len(key)
                    matched = True
                    break
            if not matched:
                pos += 1
    return expanded


def needs_bilingual_index(text: str) -> bool:
    """Return True when lexical retrieval requires CJK or 3-4 digit numeric postings."""
    return cjk_ratio(text) > 0.0 or _NUMERIC_CODE_RE.search(text) is not None

from pathlib import Path

_FILES = {
    "services/cache.py": '''"""Request cache with tenant isolation and TTL expiration."""

import hashlib
from time import monotonic
from urllib.parse import urlencode, urlsplit


def cache_key(tenant_id: str, request_path: str) -> str:
    """生成租户隔离的缓存键。对请求路径与查询参数排序后计算摘要。"""
    parsed = urlsplit(request_path)
    query = urlencode(sorted(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair))
    value = f"{tenant_id}:{parsed.path}?{query}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ResponseCache:
    """响应缓存按单调时钟判断过期时间，避免系统时钟调整导致误判。"""

    def __init__(self, ttl_seconds: int = 25) -> None:
        self.ttl_seconds = ttl_seconds
        self.entries: dict[str, tuple[float, bytes]] = {}

    def get(self, key: str) -> bytes | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if monotonic() >= expires_at:
            self.entries.pop(key, None)
            return None
        return value

    def put(self, key: str, value: bytes) -> None:
        self.entries[key] = (monotonic() + self.ttl_seconds, value)
''',
    "services/retry.py": '''"""Retry policy for upstream failures."""

from collections.abc import Mapping


def retry_delay(attempt: int, status: int, headers: Mapping[str, str]) -> float | None:
    """为网关错误 502 计算指数退避，并尊重频率限制 429 的 Retry-After 响应头。"""
    if status == 429 and headers.get("Retry-After", "").isdigit():
        return min(60.0, float(headers["Retry-After"]))
    if status in (429, 502, 503, 504):
        return min(30.0, 0.25 * 2 ** min(attempt, 8))
    return None
''',
    "services/credential_demo.py": '''"""Sample strings for scanner demonstrations only."""

# [FAKE_TEST_ONLY] These fixed examples have no account or privileges.
DEMO_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
DEMO_ALIYUN_KEY = "LTAI5tDemoFakeKey0000"
DEMO_GITHUB_TOKEN = "ghp_DemoFakeToken0000000000000000000000"
''',
    "gateway/router.ts": """type GatewayRequest = { method: string; path: string; tenantId?: string };
type GatewayResponse = { status: number; body: string };
type Handler = (request: GatewayRequest) => Promise<GatewayResponse>;

export class RequestRouter {
  private readonly routes = new Map<string, Handler>();

  public register(method: string, path: string, handler: Handler): void {
    this.routes.set(method.toUpperCase() + " " + path, handler);
  }

  // 根据请求方法和路径查找处理器。租户身份缺失时拒绝路由。
  public async dispatch(request: GatewayRequest): Promise<GatewayResponse> {
    if (!request.tenantId) {
      return { status: 401, body: "tenant identity required" };
    }
    const route = this.routes.get(request.method.toUpperCase() + " " + request.path);
    return route ? route(request) : { status: 404, body: "route missing" };
  }
}
""",
    "gateway/client.ts": """// 给上游调用增加请求超时与请求追踪标识。
export async function fetchWithTimeout(url: string, requestId: string, timeoutMs = 2500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      signal: controller.signal,
      headers: { "X-Request-Id": requestId },
    });
  } finally {
    clearTimeout(timer);
  }
}
""",
    "ratelimit/limiter.go": """package ratelimit

import (
    "sync"
    "time"
)

// RateLimiter uses a per-tenant fixed window. 超出请求频率时返回状态码 429。
type RateLimiter struct {
    mu sync.Mutex
    limit int
    window time.Duration
    tenants map[string]counter
}

type counter struct {
    start time.Time
    used int
}

func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
    return &RateLimiter{limit: limit, window: window, tenants: make(map[string]counter)}
}

// Allow 用互斥锁保护计数，窗口时间到期后重置。
func (limiter *RateLimiter) Allow(tenant string, now time.Time) bool {
    limiter.mu.Lock()
    defer limiter.mu.Unlock()
    current := limiter.tenants[tenant]
    if current.start.IsZero() || now.Sub(current.start) >= limiter.window {
        current = counter{start: now}
    }
    if current.used >= limiter.limit {
        return false
    }
    current.used++
    limiter.tenants[tenant] = current
    return true
}
""",
    "ratelimit/limiter_test.go": """package ratelimit

import (
    "testing"
    "time"
)

func TestRateLimiter(t *testing.T) {
    limiter := NewRateLimiter(1, time.Second)
    now := time.Unix(0, 0)
    if !limiter.Allow("tenant-a", now) || limiter.Allow("tenant-a", now) {
        t.Fatal("expected the second request to be rejected")
    }
}
""",
    "storage/schema.sql": """-- 持久化请求缓存条目，租户和缓存键构成联合主键。
CREATE TABLE request_cache (
    tenant_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    response_body BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, cache_key)
);

CREATE INDEX request_cache_expiration ON request_cache (expires_at);

-- 请求事件用于审计和吞吐量统计。
CREATE TABLE request_events (
    tenant_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    status_code INTEGER NOT NULL
);
""",
    "storage/queries.sql": """-- 清理已经过期的缓存记录，返回删除的租户和键。
DELETE FROM request_cache
WHERE expires_at <= CURRENT_TIMESTAMP
RETURNING tenant_id, cache_key;

-- 按租户检索有效缓存内容。
SELECT response_body
FROM request_cache
WHERE tenant_id = $1 AND cache_key = $2 AND expires_at > CURRENT_TIMESTAMP;
""",
    "tests/test_cache.py": '''from services.cache import cache_key


def test_cache_key_is_order_independent():
    """测试查询参数顺序变化时，缓存键保持一致。"""
    assert cache_key("a", "/list?page=2&sort=asc") == cache_key("a", "/list?sort=asc&page=2")
''',
    "docs/gateway.md": """# Gateway operation / 网关运维

租户请求沿着路由、频率限制和缓存依次处理。使用请求追踪标识定位超时日志。
Cache entries expire after 25 seconds in the default service configuration.
Audit findings contain masked previews and can be reviewed by rule and severity.
""",
}


def create_demo_repo(root: Path) -> Path:
    """Create an isolated bilingual fixture repository at a new local directory."""
    root.mkdir()
    for filename, content in _FILES.items():
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root

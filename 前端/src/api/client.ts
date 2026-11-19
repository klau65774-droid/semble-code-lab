import type {
  AuditResponse,
  BenchmarkResponse,
  ContentType,
  FileChunks,
  FileSummary,
  Health,
  IndexRequest,
  RelatedRequest,
  RelatedResponse,
  RepoSummary,
  SearchMode,
  SearchRequest,
  SearchResponse,
} from './types';

export const SEARCH_MODES: SearchMode[] = ['enhanced', 'baseline', 'semantic', 'bm25'];
export const CONTENT_TYPES: ContentType[] = ['code', 'docs', 'config'];

export const API_CONTRACT = {
  health: { method: 'get', path: '/api/health' },
  repos: { method: 'get', path: '/api/repos' },
  index: { method: 'post', path: '/api/repos/index' },
  search: { method: 'post', path: '/api/search' },
  files: { method: 'get', path: '/api/repos/{repo_id}/files' },
  chunks: { method: 'get', path: '/api/repos/{repo_id}/chunks' },
  related: { method: 'post', path: '/api/chunks/related' },
  benchmarks: { method: 'post', path: '/api/benchmarks/run' },
  audit: { method: 'get', path: '/api/security/audit' },
} as const;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorDetail(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return `API request failed (${status})`;
}

async function request<T>(
  endpoint: { method: 'get' | 'post'; path: string },
  options: { path?: string; query?: URLSearchParams; body?: unknown } = {},
): Promise<T> {
  const method = endpoint.method.toUpperCase() as 'GET' | 'POST';
  const init: RequestInit = { method };
  if (options.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(options.body);
  }

  const url = `${options.path ?? endpoint.path}${options.query ? `?${options.query}` : ''}`;
  const response = await fetch(url, init);
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorDetail(payload, response.status), response.status);
  return payload as T;
}

function repoPath(endpoint: { method: 'get'; path: string }, repoId: string): string {
  return endpoint.path.replace('{repo_id}', encodeURIComponent(repoId));
}

export const api = {
  health: () => request<Health>(API_CONTRACT.health),

  repos: () => request<RepoSummary[]>(API_CONTRACT.repos),

  indexRepo: (body: IndexRequest) =>
    request<RepoSummary>(API_CONTRACT.index, { body }),

  search: (body: SearchRequest) =>
    request<SearchResponse>(API_CONTRACT.search, { body }),

  files: (repoId: string) =>
    request<FileSummary[]>(API_CONTRACT.files, { path: repoPath(API_CONTRACT.files, repoId) }),

  chunks: (repoId: string, filePath: string) =>
    request<FileChunks>(API_CONTRACT.chunks, {
      path: repoPath(API_CONTRACT.chunks, repoId),
      query: new URLSearchParams({ file_path: filePath }),
    }),

  related: (body: RelatedRequest) =>
    request<RelatedResponse>(API_CONTRACT.related, { body }),

  benchmarks: () => request<BenchmarkResponse>(API_CONTRACT.benchmarks),

  audit: (repoId?: string) =>
    request<AuditResponse>(API_CONTRACT.audit, {
      query: repoId ? new URLSearchParams({ repo_id: repoId }) : undefined,
    }),
};

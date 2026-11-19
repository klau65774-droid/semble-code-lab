import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../client';

const fetchMock = vi.fn();

function mockJson(payload: unknown = {}, ok = true, status = 200) {
  fetchMock.mockResolvedValue({
    ok,
    status,
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response);
}

beforeEach(() => {
  mockJson();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe('typed API client', () => {
  it('uses relative URLs and serializes the core request bodies', async () => {
    await api.search({
      repo_id: 'semble-core',
      query: 'hybrid search',
      mode: 'enhanced',
      alpha: 0.4,
      compare_baseline: true,
    });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_id: 'semble-core',
        query: 'hybrid search',
        mode: 'enhanced',
        alpha: 0.4,
        compare_baseline: true,
      }),
    });

    await api.indexRepo({ path: 'D:/workspace/semble', force_rebuild: true });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: 'D:/workspace/semble', force_rebuild: true }),
    });

    await api.related({ repo_id: 'semble-core', file_path: 'src/search.py', line: 18, top_k: 5 });
    expect(fetchMock).toHaveBeenLastCalledWith('/api/chunks/related', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_id: 'semble-core', file_path: 'src/search.py', line: 18, top_k: 5 }),
    });
  });

  it('encodes path parameters and file query parameters', async () => {
    await api.files('repo id');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/repo%20id/files', { method: 'GET' });

    await api.chunks('semble-core', 'src/a b.py');
    const [url] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe('/api/repos/semble-core/chunks?file_path=src%2Fa+b.py');
  });

  it('uses the declared methods for health, repositories, benchmarks, and audit', async () => {
    await api.health();
    expect(fetchMock).toHaveBeenLastCalledWith('/api/health', { method: 'GET' });
    await api.repos();
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos', { method: 'GET' });
    await api.benchmarks();
    expect(fetchMock).toHaveBeenLastCalledWith('/api/benchmarks/run', { method: 'POST' });
    await api.audit('bilingual-demo');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/security/audit?repo_id=bilingual-demo', { method: 'GET' });
    await api.audit();
    expect(fetchMock).toHaveBeenLastCalledWith('/api/security/audit', { method: 'GET' });
  });

  it('surfaces sanitized backend error details', async () => {
    mockJson({ detail: 'Repository not found' }, false, 404);
    const request = api.repos();
    await expect(request).rejects.toEqual(new ApiError('Repository not found', 404));
  });
});

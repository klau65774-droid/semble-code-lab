import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../../api/client';
import { relatedResponse, repos, searchResponse } from '../../../test/fixtures';
import { SearchWorkspace } from '../SearchWorkspace';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return {
    ...actual,
    api: {
      search: vi.fn(),
      related: vi.fn(),
    },
  };
});

const searchMock = vi.mocked(api.search);
const relatedMock = vi.mocked(api.related);

function renderWorkspace(onRepoChange = vi.fn(), onLatency = vi.fn()) {
  return {
    onRepoChange,
    onLatency,
    ...render(
      <SearchWorkspace
        repos={repos}
        activeRepoId="semble-core"
        onRepoChange={onRepoChange}
        onLatency={onLatency}
      />,
    ),
  };
}

beforeEach(() => {
  searchMock.mockReset().mockResolvedValue(searchResponse);
  relatedMock.mockReset().mockResolvedValue(relatedResponse);
});

describe('SearchWorkspace', () => {
  it('runs the reference query and renders explained, redacted results', async () => {
    const { onLatency } = renderWorkspace();

    await screen.findByText('semble/index/sparse.py');
    expect(searchMock).toHaveBeenCalledWith(
      expect.objectContaining({ repo_id: 'semble-core', query: 'where is enrich_for_bm25 defined' }),
    );
    expect(onLatency).toHaveBeenCalledWith(1.3);
    expect(screen.getByText('91.4%')).toBeInTheDocument();
    expect(screen.getByText('+2 vs Baseline')).toBeInTheDocument();
    expect(screen.getByText('-1 vs Baseline')).toBeInTheDocument();
    expect(screen.getByText('SCORE DECOMPOSITION')).toBeInTheDocument();
    expect(screen.getAllByText(/REDACTED/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/PLAINTEXT_MUST_NOT_RENDER/)).not.toBeInTheDocument();
  });

  it('serializes mode, comparison, alpha, token, rerank, and redaction controls', async () => {
    renderWorkspace();
    await screen.findByText('semble/index/sparse.py');
    searchMock.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'BM25' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Compare Baseline A/B' }));
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }));
    fireEvent.change(screen.getByRole('slider', { name: 'Alpha fusion' }), { target: { value: '0.65' } });
    fireEvent.click(screen.getByRole('button', { name: 'Unlimited' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Rerank' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Redact Secrets' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search query' }), {
      target: { value: 'hybrid fusion' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(searchMock).toHaveBeenCalledOnce());
    expect(searchMock).toHaveBeenCalledWith({
      repo_id: 'semble-core',
      query: 'hybrid fusion',
      top_k: 8,
      mode: 'bm25',
      alpha: 0.65,
      rerank: false,
      token_budget: null,
      redact_secrets: false,
      compare_baseline: false,
    });
  });

  it('applies a cross-repository secret preset and triggers its search', async () => {
    const { onRepoChange } = renderWorkspace();
    await screen.findByText('semble/index/sparse.py');
    searchMock.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Secret Audit' }));

    expect(onRepoChange).toHaveBeenCalledWith('bilingual-demo');
    await waitFor(() => expect(searchMock).toHaveBeenCalledOnce());
    expect(searchMock).toHaveBeenCalledWith(
      expect.objectContaining({ repo_id: 'bilingual-demo', query: expect.stringMatching(/database|credential/i) }),
    );
  });

  it('loads related chunks for the focused result', async () => {
    renderWorkspace();
    await screen.findByText('semble/index/sparse.py');

    fireEvent.click(screen.getAllByRole('button', { name: 'Find Related' })[0]);

    await screen.findByText('semble/index/fusion.py');
    expect(relatedMock).toHaveBeenCalledWith({
      repo_id: 'semble-core',
      file_path: 'semble/index/sparse.py',
      line: 18,
      top_k: 5,
    });
    expect(screen.getByText('0.870')).toBeInTheDocument();
  });

  it('renders empty and failure states without stale results', async () => {
    searchMock.mockResolvedValueOnce({
      ...searchResponse,
      results: [],
      baseline_comparison: null,
      savings_pct: null,
      full_file_tokens: null,
    });
    const { unmount } = renderWorkspace();
    await screen.findByText('No matching chunks');
    expect(screen.getByText('Enable Compare Baseline A/B to inspect rank movement.')).toBeInTheDocument();
    unmount();

    searchMock.mockRejectedValueOnce(new Error('Backend offline'));
    renderWorkspace();
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend offline');
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../../api/client';
import { auditResponse, benchmarkResponse, repos } from '../../../test/fixtures';
import { BenchmarksWorkspace } from '../BenchmarksWorkspace';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return {
    ...actual,
    api: {
      benchmarks: vi.fn(),
      audit: vi.fn(),
    },
  };
});

const benchmarkMock = vi.mocked(api.benchmarks);
const auditMock = vi.mocked(api.audit);

beforeEach(() => {
  benchmarkMock.mockReset().mockResolvedValue(benchmarkResponse);
  auditMock.mockReset().mockResolvedValue(auditResponse);
});

describe('BenchmarksWorkspace', () => {
  it('loads cross-repository sanitized audit findings without running benchmarks implicitly', async () => {
    render(<BenchmarksWorkspace repos={repos} />);

    expect(await screen.findByText('DATABASE_URL = "postgresql://[REDACTED]"')).toBeInTheDocument();
    expect(screen.getByText('AWS_ACCESS_KEY_ID = "[REDACTED]"')).toBeInTheDocument();
    expect(auditMock).toHaveBeenCalledWith();
    expect(benchmarkMock).not.toHaveBeenCalled();
    expect(screen.getByText('No benchmark run yet')).toBeInTheDocument();
    expect(screen.queryByText(/PLAINTEXT/)).not.toBeInTheDocument();
  });

  it('runs the four-mode benchmark and renders metrics and per-query winners', async () => {
    render(<BenchmarksWorkspace repos={repos} />);
    fireEvent.click(screen.getByRole('button', { name: 'Run Offline Benchmark Suite' }));

    await waitFor(() => expect(benchmarkMock).toHaveBeenCalledOnce());
    expect(await screen.findByText('where is enrich_for_bm25 defined')).toBeInTheDocument();
    expect(screen.getAllByText('NDCG@10').length).toBeGreaterThan(0);
    expect(screen.getAllByText('0.890').length).toBeGreaterThan(0);
    expect(screen.getByText('Enhanced leads')).toBeInTheDocument();
    expect(screen.getByText(/N 1\.000 · M 1\.000 · R 1\.000/)).toBeInTheDocument();
  });

  it('filters the audit through the backend repo_id query parameter', async () => {
    render(<BenchmarksWorkspace repos={repos} />);
    await screen.findByText('DATABASE_URL = "postgresql://[REDACTED]"');

    fireEvent.change(screen.getByRole('combobox', { name: 'Audit repository scope' }), {
      target: { value: 'bilingual-demo' },
    });

    await waitFor(() => expect(auditMock).toHaveBeenCalledWith('bilingual-demo'));
    auditMock.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh security audit' }));
    await waitFor(() => expect(auditMock).toHaveBeenCalledWith('bilingual-demo'));
  });

  it('renders empty benchmark and audit states', async () => {
    auditMock.mockResolvedValue({ total_findings: 0, files_affected: 0, by_rule: {}, by_severity: {}, findings: [] });
    benchmarkMock.mockResolvedValue({ ...benchmarkResponse, query_count: 0, queries: [] });
    render(<BenchmarksWorkspace repos={repos} />);

    expect(await screen.findByText('No credential findings')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run Offline Benchmark Suite' }));
    expect(await screen.findByText('No benchmark queries')).toBeInTheDocument();
  });

  it('surfaces audit and benchmark failures independently', async () => {
    auditMock.mockRejectedValue(new Error('Audit unavailable'));
    benchmarkMock.mockRejectedValue(new Error('Benchmark conflict'));
    render(<BenchmarksWorkspace repos={repos} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Audit unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Run Offline Benchmark Suite' }));
    await screen.findByText('Benchmark conflict');
    expect(screen.getAllByRole('alert')).toHaveLength(2);
  });
});

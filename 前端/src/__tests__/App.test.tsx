import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import {
  auditResponse,
  fileChunks,
  files,
  health,
  relatedResponse,
  repos,
  searchResponse,
} from '../test/fixtures';
import { App } from '../App';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    api: {
      health: vi.fn(),
      repos: vi.fn(),
      indexRepo: vi.fn(),
      search: vi.fn(),
      files: vi.fn(),
      chunks: vi.fn(),
      related: vi.fn(),
      benchmarks: vi.fn(),
      audit: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.mocked(api.health).mockReset().mockResolvedValue(health);
  vi.mocked(api.repos).mockReset().mockResolvedValue(repos);
  vi.mocked(api.indexRepo).mockReset().mockResolvedValue(repos[0]);
  vi.mocked(api.search).mockReset().mockResolvedValue(searchResponse);
  vi.mocked(api.files).mockReset().mockResolvedValue(files);
  vi.mocked(api.chunks).mockReset().mockResolvedValue(fileChunks);
  vi.mocked(api.related).mockReset().mockResolvedValue(relatedResponse);
  vi.mocked(api.benchmarks).mockReset();
  vi.mocked(api.audit).mockReset().mockResolvedValue(auditResponse);
});

describe('App integration', () => {
  it('shares repository and health state across all three workspaces', async () => {
    render(<App />);

    expect(await screen.findByText('semble/index/sparse.py')).toBeInTheDocument();
    expect(screen.getByText('API ONLINE')).toBeInTheDocument();
    expect(screen.getByText('1.3ms CPU')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '02 AST Inspector' }));
    expect(await screen.findByText('L18-29')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '03 Benchmarks & Audit' }));
    expect(await screen.findByText('DATABASE_URL = "postgresql://[REDACTED]"')).toBeInTheDocument();
  });

  it('keeps the shell usable when the API is offline', async () => {
    vi.mocked(api.health).mockRejectedValue(new Error('offline'));
    vi.mocked(api.repos).mockRejectedValue(new Error('Connection refused'));
    render(<App />);

    expect(await screen.findByText('API OFFLINE')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Connection refused');
    expect(screen.getByText('No repository selected')).toBeInTheDocument();
    expect(api.search).not.toHaveBeenCalled();
  });
});

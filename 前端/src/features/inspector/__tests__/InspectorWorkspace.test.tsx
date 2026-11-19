import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../../api/client';
import { fileChunks, files, repos } from '../../../test/fixtures';
import { InspectorWorkspace } from '../InspectorWorkspace';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return {
    ...actual,
    api: {
      files: vi.fn(),
      chunks: vi.fn(),
      indexRepo: vi.fn(),
    },
  };
});

const filesMock = vi.mocked(api.files);
const chunksMock = vi.mocked(api.chunks);
const indexMock = vi.mocked(api.indexRepo);

beforeEach(() => {
  filesMock.mockReset().mockResolvedValue(files);
  chunksMock.mockReset().mockResolvedValue(fileChunks);
  indexMock.mockReset().mockResolvedValue(repos[0]);
});

describe('InspectorWorkspace', () => {
  it('loads file metadata and the first file AST chunks', async () => {
    render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={vi.fn()} />);

    expect(await screen.findByText('L18-29')).toBeInTheDocument();
    expect(screen.getByText('L31-48')).toBeInTheDocument();
    expect(screen.getAllByText('enrich_for_bm25')).toHaveLength(2);
    expect(screen.getByText('0.30x Test Penalty')).toBeInTheDocument();
    expect(screen.getByText('2 secrets')).toBeInTheDocument();
    expect(filesMock).toHaveBeenCalledWith('semble-core');
    expect(chunksMock).toHaveBeenCalledWith('semble-core', 'semble/index/sparse.py');
  });

  it('loads chunks when another file is selected', async () => {
    chunksMock
      .mockResolvedValueOnce(fileChunks)
      .mockResolvedValue({ ...fileChunks, file_path: 'tests/test_search.py', chunks: [] });
    render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={vi.fn()} />);
    await screen.findByText('L18-29');

    fireEvent.click(screen.getByRole('button', { name: /tests\/test_search.py/ }));

    await waitFor(() => expect(chunksMock).toHaveBeenCalledWith('semble-core', 'tests/test_search.py'));
    expect(await screen.findByText('This file has no AST chunks.')).toBeInTheDocument();
  });

  it('validates indexing input before calling the backend', async () => {
    render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={vi.fn()} />);
    await screen.findByText('L18-29');

    fireEvent.change(screen.getByRole('textbox', { name: 'Local repository path' }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Index Repository' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Local repository path is required');
    expect(indexMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('textbox', { name: 'Local repository path' }), { target: { value: 'D:/workspace/semble-core' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Repository ID (optional)' }), { target: { value: 'bad id' } });
    fireEvent.click(screen.getByRole('button', { name: 'Index Repository' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Repository ID must match');
    expect(indexMock).not.toHaveBeenCalled();
  });

  it('indexes and force-rebuilds a valid repository', async () => {
    const onRepoIndexed = vi.fn();
    render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={onRepoIndexed} />);
    await screen.findByText('L18-29');

    fireEvent.change(screen.getByRole('textbox', { name: 'Repository ID (optional)' }), { target: { value: 'semble-core' } });
    fireEvent.click(screen.getByRole('switch', { name: 'Force rebuild' }));
    fireEvent.click(screen.getByRole('button', { name: 'Index Repository' }));

    await waitFor(() => expect(indexMock).toHaveBeenCalledWith({
      path: 'D:/workspace/semble-core',
      repo_id: 'semble-core',
      force_rebuild: true,
    }));
    expect(onRepoIndexed).toHaveBeenCalledWith(repos[0]);
    expect(await screen.findByText(/Indexed 29 files/)).toBeInTheDocument();
  });

  it('renders empty and file-loading failure states', async () => {
    filesMock.mockResolvedValueOnce([]);
    const { unmount } = render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={vi.fn()} />);
    expect(await screen.findByText('No indexed files')).toBeInTheDocument();
    expect(chunksMock).not.toHaveBeenCalled();
    unmount();

    filesMock.mockRejectedValueOnce(new Error('Snapshot unavailable'));
    render(<InspectorWorkspace repo={repos[0]} onRepoIndexed={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Snapshot unavailable');
  });
});

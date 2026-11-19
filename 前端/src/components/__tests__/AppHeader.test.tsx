import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { health, repos } from '../../test/fixtures';
import { AppHeader } from '../AppHeader';

describe('AppHeader', () => {
  it('renders repository metadata, tabs, and online telemetry', () => {
    render(
      <AppHeader
        repos={repos}
        activeRepoId="semble-core"
        activeTab="search"
        health={health}
        healthError={false}
        lastLatency={1.3}
        onRepoChange={vi.fn()}
        onTabChange={vi.fn()}
        onRefreshHealth={vi.fn()}
      />,
    );

    expect(screen.getByText('SEMBLE')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Active repository' })).toHaveDisplayValue(
      'semble-core · 29 files · 320 AST chunks',
    );
    expect(screen.getByRole('tab', { name: '01 Search & Diff' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('API ONLINE');
    expect(screen.getByRole('status')).toHaveTextContent('1.3ms CPU');
  });

  it('emits tab, repository, and health refresh actions', () => {
    const onTabChange = vi.fn();
    const onRepoChange = vi.fn();
    const onRefreshHealth = vi.fn();
    render(
      <AppHeader
        repos={repos}
        activeRepoId="semble-core"
        activeTab="search"
        health={health}
        healthError={false}
        lastLatency={null}
        onRepoChange={onRepoChange}
        onTabChange={onTabChange}
        onRefreshHealth={onRefreshHealth}
      />,
    );

    fireEvent.click(screen.getByRole('tab', { name: '02 AST Inspector' }));
    expect(onTabChange).toHaveBeenCalledWith('inspector');
    fireEvent.change(screen.getByRole('combobox', { name: 'Active repository' }), {
      target: { value: 'bilingual-demo' },
    });
    expect(onRepoChange).toHaveBeenCalledWith('bilingual-demo');
    fireEvent.click(screen.getByRole('button', { name: 'Refresh API health' }));
    expect(onRefreshHealth).toHaveBeenCalledOnce();
  });

  it('shows an offline state without inventing latency', () => {
    render(
      <AppHeader
        repos={[]}
        activeRepoId=""
        activeTab="benchmarks"
        health={null}
        healthError
        lastLatency={null}
        onRepoChange={vi.fn()}
        onTabChange={vi.fn()}
        onRefreshHealth={vi.fn()}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('API OFFLINE');
    expect(screen.queryByText(/ms CPU/)).not.toBeInTheDocument();
  });
});

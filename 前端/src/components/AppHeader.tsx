import type { Health, RepoSummary } from '../api/types';
import { formatMs } from '../lib/format';
import { cx, Icon } from './ui';

export type WorkspaceTab = 'search' | 'inspector' | 'benchmarks';

const tabs: Array<{ id: WorkspaceTab; label: string }> = [
  { id: 'search', label: '01 Search & Diff' },
  { id: 'inspector', label: '02 AST Inspector' },
  { id: 'benchmarks', label: '03 Benchmarks & Audit' },
];

export function AppHeader({
  repos,
  activeRepoId,
  activeTab,
  health,
  healthError,
  lastLatency,
  onRepoChange,
  onTabChange,
  onRefreshHealth,
}: {
  repos: RepoSummary[];
  activeRepoId: string;
  activeTab: WorkspaceTab;
  health: Health | null;
  healthError: boolean;
  lastLatency: number | null;
  onRepoChange: (repoId: string) => void;
  onTabChange: (tab: WorkspaceTab) => void;
  onRefreshHealth: () => void;
}) {
  const online = Boolean(health && !healthError);

  return (
    <header className="app-header">
      <div className="brand" aria-label="SEMBLE Code Lab">
        <span className="brand__mark"><Icon name="layers" size={17} /></span>
        <span className="brand__name">SEMBLE</span>
        <span className="brand__suffix">// CODE LAB</span>
      </div>

      <div className="repo-select">
        <Icon name="database" size={14} />
        <select
          aria-label="Active repository"
          disabled={repos.length === 0}
          onChange={(event) => onRepoChange(event.target.value)}
          value={activeRepoId}
        >
          {repos.length === 0 ? (
            <option value="">No indexed repositories</option>
          ) : (
            repos.map((repo) => (
              <option key={repo.repo_id} value={repo.repo_id}>
                {repo.name} · {repo.indexed_files} files · {repo.total_chunks} AST chunks
              </option>
            ))
          )}
        </select>
        <Icon className="repo-select__chevron" name="chevron-down" size={12} />
      </div>

      <nav className="workspace-tabs" aria-label="Workspaces" role="tablist">
        {tabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.id}
            className={cx('workspace-tab', activeTab === tab.id && 'workspace-tab--active')}
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className={cx('health-pill', online ? 'health-pill--online' : healthError && 'health-pill--offline')}>
        <span className="health-pill__status" role="status">
          <span className="status-dot" />
          {healthError ? 'API OFFLINE' : health ? 'API ONLINE' : 'API CHECKING'}
          {online && lastLatency != null && <span className="health-pill__latency">{formatMs(lastLatency)} CPU</span>}
        </span>
        <button aria-label="Refresh API health" onClick={onRefreshHealth} title="Refresh API health" type="button">
          <Icon name="refresh" size={12} />
        </button>
      </div>
    </header>
  );
}

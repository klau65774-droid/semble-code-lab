import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import type { Health, RepoSummary } from './api/types';
import { AppHeader } from './components/AppHeader';
import type { WorkspaceTab } from './components/AppHeader';
import { ErrorState } from './components/ui';
import { BenchmarksWorkspace } from './features/benchmarks/BenchmarksWorkspace';
import { InspectorWorkspace } from './features/inspector/InspectorWorkspace';
import { SearchWorkspace } from './features/search/SearchWorkspace';
import { errorMessage } from './lib/format';

export function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('search');
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [activeRepoId, setActiveRepoId] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);
  const [lastLatency, setLastLatency] = useState<number | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(false);
    } catch {
      setHealth(null);
      setHealthError(true);
    }
  }, []);

  const refreshRepos = useCallback(async () => {
    try {
      const data = await api.repos();
      setRepos(data);
      setActiveRepoId((current) => data.some((repo) => repo.repo_id === current) ? current : data[0]?.repo_id ?? '');
      setRepoError(null);
    } catch (error) {
      setRepoError(errorMessage(error));
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    void refreshRepos();
    const interval = window.setInterval(() => void refreshHealth(), 15_000);
    return () => window.clearInterval(interval);
  }, [refreshHealth, refreshRepos]);

  const handleRepoIndexed = useCallback((indexed: RepoSummary) => {
    setRepos((current) => {
      const exists = current.some((repo) => repo.repo_id === indexed.repo_id);
      return exists
        ? current.map((repo) => repo.repo_id === indexed.repo_id ? indexed : repo)
        : [...current, indexed];
    });
    setActiveRepoId(indexed.repo_id);
    setRepoError(null);
    void refreshHealth();
  }, [refreshHealth]);

  const activeRepo = repos.find((repo) => repo.repo_id === activeRepoId) ?? null;

  return (
    <div className="app-shell">
      <AppHeader
        activeRepoId={activeRepoId}
        activeTab={activeTab}
        health={health}
        healthError={healthError}
        lastLatency={lastLatency}
        onRefreshHealth={() => void refreshHealth()}
        onRepoChange={setActiveRepoId}
        onTabChange={setActiveTab}
        repos={repos}
      />
      {repoError && (
        <div className="global-api-error">
          <ErrorState message={repoError} onRetry={() => void refreshRepos()} />
        </div>
      )}
      {activeTab === 'search' && (
        <SearchWorkspace
          activeRepoId={activeRepoId}
          onLatency={setLastLatency}
          onRepoChange={setActiveRepoId}
          repos={repos}
        />
      )}
      {activeTab === 'inspector' && (
        <InspectorWorkspace onRepoIndexed={handleRepoIndexed} repo={activeRepo} />
      )}
      {activeTab === 'benchmarks' && <BenchmarksWorkspace repos={repos} />}
    </div>
  );
}

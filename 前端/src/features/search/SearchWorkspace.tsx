import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { ExplainedSearchResult, RelatedResponse, RepoSummary, SearchResponse } from '../../api/types';
import { EmptyState } from '../../components/ui';
import { errorMessage } from '../../lib/format';
import { DEFAULT_SEARCH_SETTINGS, PRESET_QUERIES, SearchControls } from './SearchControls';
import type { SearchSettings } from './SearchControls';
import { SearchResults } from './SearchResults';
import { TelemetryPanel } from './TelemetryPanel';

export function SearchWorkspace({
  repos,
  activeRepoId,
  onRepoChange,
  onLatency,
}: {
  repos: RepoSummary[];
  activeRepoId: string;
  onRepoChange: (repoId: string) => void;
  onLatency: (latency: number) => void;
}) {
  const [query, setQuery] = useState('where is enrich_for_bm25 defined');
  const [settings, setSettings] = useState<SearchSettings>(DEFAULT_SEARCH_SETTINGS);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [related, setRelated] = useState<RelatedResponse | null>(null);
  const [relatedLoading, setRelatedLoading] = useState(false);
  const [relatedError, setRelatedError] = useState<string | null>(null);
  const lastRepoRef = useRef('');
  const searchRequestRef = useRef(0);
  const relatedRequestRef = useRef(0);

  async function performSearch(override?: { repoId: string; query: string }) {
    const repoId = override?.repoId ?? activeRepoId;
    const nextQuery = override?.query ?? query;
    if (!repoId || !nextQuery.trim()) {
      if (!repoId) setError('Index or select a repository before searching.');
      return;
    }

    const requestId = ++searchRequestRef.current;
    setLoading(true);
    setError(null);
    setResponse(null);
    setSelectedChunkId(null);
    setRelated(null);
    setRelatedError(null);

    try {
      const result = await api.search({
        repo_id: repoId,
        query: nextQuery.trim(),
        top_k: 8,
        mode: settings.mode,
        alpha: settings.alphaAuto ? null : settings.alpha,
        rerank: settings.rerank,
        token_budget: settings.tokenUnlimited ? null : settings.tokenBudget,
        redact_secrets: settings.redactSecrets,
        compare_baseline: settings.compareBaseline,
      });
      if (requestId !== searchRequestRef.current) return;
      setResponse(result);
      setSelectedChunkId(result.results[0]?.chunk_id ?? null);
      onLatency(result.latency_ms);
    } catch (requestError) {
      if (requestId !== searchRequestRef.current) return;
      setError(errorMessage(requestError));
    } finally {
      if (requestId === searchRequestRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    if (!activeRepoId) {
      lastRepoRef.current = '';
      setResponse(null);
      return;
    }
    if (lastRepoRef.current !== activeRepoId) {
      lastRepoRef.current = activeRepoId;
      void performSearch();
    }
    // Repository changes intentionally rerun the current query; preset searches set the ref first.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRepoId]);

  function selectPreset(preset: (typeof PRESET_QUERIES)[number]) {
    lastRepoRef.current = preset.repoId;
    onRepoChange(preset.repoId);
    setQuery(preset.query);
    void performSearch({ repoId: preset.repoId, query: preset.query });
  }

  function selectResult(result: ExplainedSearchResult) {
    setSelectedChunkId(result.chunk_id);
    setRelated(null);
    setRelatedError(null);
  }

  async function findRelated(result: ExplainedSearchResult) {
    selectResult(result);
    const requestId = ++relatedRequestRef.current;
    setRelatedLoading(true);
    setRelatedError(null);
    try {
      const data = await api.related({
        repo_id: activeRepoId,
        file_path: result.chunk.file_path,
        line: result.chunk.start_line,
        top_k: 5,
      });
      if (requestId !== relatedRequestRef.current) return;
      setRelated(data);
    } catch (requestError) {
      if (requestId === relatedRequestRef.current) setRelatedError(errorMessage(requestError));
    } finally {
      if (requestId === relatedRequestRef.current) setRelatedLoading(false);
    }
  }

  const selected = response?.results.find((result) => result.chunk_id === selectedChunkId) ?? response?.results[0] ?? null;

  if (!activeRepoId) {
    return (
      <div className="workspace-empty">
        <EmptyState title="No repository selected" detail="The backend has not reported an indexed snapshot. Use AST Inspector to index an allowed local directory." />
      </div>
    );
  }

  return (
    <div className="search-grid">
      <SearchControls
        activeRepoId={activeRepoId}
        availableRepoIds={repos.map((repo) => repo.repo_id)}
        onPreset={selectPreset}
        onSettingsChange={(patch) => setSettings((current) => ({ ...current, ...patch }))}
        response={response}
        settings={settings}
      />
      <SearchResults
        error={error}
        loading={loading}
        onQueryChange={setQuery}
        onRelated={(result) => void findRelated(result)}
        onRetry={() => void performSearch()}
        onSearch={() => void performSearch()}
        onSelect={selectResult}
        query={query}
        response={response}
        selectedChunkId={selectedChunkId}
      />
      <TelemetryPanel
        onRelatedRetry={() => selected && void findRelated(selected)}
        related={related}
        relatedError={relatedError}
        relatedLoading={relatedLoading}
        response={response}
        selected={selected}
      />
    </div>
  );
}

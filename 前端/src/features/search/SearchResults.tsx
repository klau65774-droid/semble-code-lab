import type { ExplainedSearchResult, SearchResponse } from '../../api/types';
import { CodeBlock } from '../../components/CodeBlock';
import { Badge, cx, EmptyState, ErrorState, Icon, LoadingState } from '../../components/ui';
import { formatMs } from '../../lib/format';
import { ScoreWaterfall } from './ScoreBreakdown';

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ResultCard({
  result,
  selected,
  rankDelta,
  onSelect,
  onRelated,
}: {
  result: ExplainedSearchResult;
  selected: boolean;
  rankDelta: number | null | undefined;
  onSelect: () => void;
  onRelated: () => void;
}) {
  return (
    <article
      className={cx('result-card', selected && 'result-card--selected')}
      onClick={onSelect}
      aria-label={`Result ${result.rank}, ${result.chunk.file_path}`}
    >
      <header className="result-card__header">
        <button className="result-card__focus" onClick={onSelect} type="button">
          <span className="result-card__rank">#{result.rank}</span>
          {rankDelta != null && (
            <Badge tone={rankDelta > 0 ? 'emerald' : rankDelta < 0 ? 'rose' : 'neutral'}>
              {rankDelta > 0 ? '+' : ''}{rankDelta} vs Baseline
            </Badge>
          )}
          <span className="result-card__path">
            {result.chunk.file_path}
            <span className="result-card__lines"> : L{result.chunk.start_line}-{result.chunk.end_line}</span>
          </span>
        </button>
        <span className="result-card__language">{titleCase(result.chunk.language ?? 'text')}</span>
      </header>

      <CodeBlock
        content={result.redacted_content}
        secretsRedacted={result.secrets_redacted}
        startLine={result.chunk.start_line}
      />

      <div className="result-card__footer">
        <ScoreWaterfall result={result} />
        <button
          className="related-button"
          onClick={(event) => {
            event.stopPropagation();
            onRelated();
          }}
          type="button"
        >
          <Icon name="branch" size={12} />
          Find Related
        </button>
      </div>
    </article>
  );
}

export function SearchResults({
  response,
  loading,
  error,
  query,
  selectedChunkId,
  onQueryChange,
  onSearch,
  onSelect,
  onRelated,
  onRetry,
}: {
  response: SearchResponse | null;
  loading: boolean;
  error: string | null;
  query: string;
  selectedChunkId: string | null;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  onSelect: (result: ExplainedSearchResult) => void;
  onRelated: (result: ExplainedSearchResult) => void;
  onRetry: () => void;
}) {
  const deltas = new Map(
    response?.baseline_comparison?.rank_deltas.map((delta) => [delta.chunk_id, delta.rank_delta]) ?? [],
  );
  const secrets = response?.results.reduce((sum, result) => sum + result.secrets_redacted, 0) ?? 0;

  return (
    <main className="search-results">
      <form
        className="search-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <div className="search-form__input">
          <Icon name="search" size={15} />
          <input
            aria-label="Search query"
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Ask for a symbol, behavior, or implementation…"
            value={query}
          />
        </div>
        <button className="primary-button search-form__button" disabled={loading || !query.trim()} type="submit">
          {loading ? <span className="loading-state__dot" /> : <Icon name="search" size={14} />}
          {loading ? 'Searching' : 'Search'}
        </button>
      </form>

      {response && (
        <div className="query-chips" aria-label="Parsed query telemetry">
          <Badge tone="blue">Type: {titleCase(response.query_type)}</Badge>
          <Badge tone={response.detected_symbols.length ? 'cyan' : 'neutral'} className="query-chip--ellipsis">
            <span>Symbols:</span> {response.detected_symbols.join(', ') || '—'}
          </Badge>
          <Badge>Tokens: {response.tokens.length}</Badge>
          <Badge tone="purple">Alpha: {response.alpha_used.toFixed(2)}</Badge>
          <Badge>Latency: {formatMs(response.latency_ms)}</Badge>
          <Badge tone={secrets ? 'rose' : 'emerald'}>Secrets Redacted: {secrets}</Badge>
        </div>
      )}

      {error && <ErrorState message={error} onRetry={onRetry} />}
      {loading && !response && <LoadingState label="Fusing dense and lexical rankings" />}
      {!loading && !error && !response && (
        <EmptyState title="Search the indexed codebase" detail="Use a natural-language query, embedded snake_case symbol, or one of the preset experiments." />
      )}
      {response && !loading && response.results.length === 0 && (
        <EmptyState title="No matching chunks" detail="Try a broader query, another retrieval mode, or a different repository." />
      )}

      <div className={cx('result-list', loading && 'result-list--loading')}>
        {response?.results.map((result) => (
          <ResultCard
            key={result.chunk_id}
            onRelated={() => onRelated(result)}
            onSelect={() => onSelect(result)}
            rankDelta={deltas.get(result.chunk_id)}
            result={result}
            selected={selectedChunkId === result.chunk_id}
          />
        ))}
      </div>
    </main>
  );
}

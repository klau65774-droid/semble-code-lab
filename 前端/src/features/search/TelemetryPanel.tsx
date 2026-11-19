import type { ExplainedSearchResult, RelatedResponse, SearchResponse } from '../../api/types';
import { Badge, EmptyState, ErrorState, Icon, LoadingState, Panel } from '../../components/ui';
import { baseName, formatMs, formatNumber, formatRank, formatScore } from '../../lib/format';
import { ScoreDecomposition } from './ScoreBreakdown';

export function TelemetryPanel({
  response,
  selected,
  related,
  relatedLoading,
  relatedError,
  onRelatedRetry,
}: {
  response: SearchResponse | null;
  selected: ExplainedSearchResult | null;
  related: RelatedResponse | null;
  relatedLoading: boolean;
  relatedError: string | null;
  onRelatedRetry: () => void;
}) {
  const deltas = response?.baseline_comparison?.rank_deltas ?? [];
  const secrets = response?.results.reduce((sum, result) => sum + result.secrets_redacted, 0) ?? 0;

  return (
    <aside className="telemetry-column">
      <Panel title="BASELINE vs ENHANCED DIFF" className="telemetry-panel">
        <div className="diff-table">
          {!response?.baseline_comparison ? (
            <div className="telemetry-empty">Enable Compare Baseline A/B to inspect rank movement.</div>
          ) : deltas.length === 0 ? (
            <div className="telemetry-empty">No rank changes reported for this query.</div>
          ) : (
            <>
              <div className="diff-table__header"><span>Chunk</span><span>Baseline → Enhanced</span></div>
              {deltas.map((delta) => (
                <div className="diff-row" key={delta.chunk_id}>
                  <div>
                    <strong>{baseName(delta.file_path)}</strong>
                    <span>L{delta.start_line}-{delta.end_line}</span>
                  </div>
                  <div className="diff-row__ranks">
                    <span>{formatRank(delta.baseline_rank)}</span>
                    <span className="diff-row__arrow">→</span>
                    <strong>{formatRank(delta.primary_rank)}</strong>
                    {delta.rank_delta != null && (
                      <Badge tone={delta.rank_delta > 0 ? 'emerald' : delta.rank_delta < 0 ? 'rose' : 'neutral'}>
                        {delta.rank_delta > 0 ? '+' : ''}{delta.rank_delta}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </Panel>

      <Panel title="SCORE DECOMPOSITION" className="telemetry-panel">
        {selected ? (
          <div>
            <div className="decomposition__source">
              <span>{baseName(selected.chunk.file_path)}</span>
              <span>L{selected.chunk.start_line}-{selected.chunk.end_line}</span>
            </div>
            <ScoreDecomposition result={selected} />
          </div>
        ) : (
          <EmptyState title="Select a result" detail="Its ranking evidence will appear here." />
        )}
      </Panel>

      <Panel
        title={related ? 'RELATED CHUNKS' : 'RETRIEVAL SNAPSHOT'}
        className="telemetry-panel telemetry-panel--snapshot"
        action={related && <Badge tone="purple">{related.results.length} NEIGHBORS</Badge>}
      >
        {relatedLoading ? (
          <LoadingState label="Searching embedding neighbors" />
        ) : relatedError ? (
          <ErrorState message={relatedError} onRetry={onRelatedRetry} />
        ) : related ? (
          <div className="related-list">
            {related.results.length === 0 ? (
              <div className="telemetry-empty">No neighboring chunks found.</div>
            ) : related.results.map((result) => (
              <article className="related-chunk" key={result.chunk_id}>
                <div className="related-chunk__title">
                  <Icon name="branch" size={12} />
                  <strong>{result.chunk.file_path}</strong>
                  <span>{formatScore(result.score)}</span>
                </div>
                <div className="related-chunk__meta">
                  <span>L{result.chunk.start_line}-{result.chunk.end_line}</span>
                  <span>{formatNumber(result.estimated_tokens)} tokens</span>
                  {result.secrets_redacted > 0 && <Badge tone="rose">{result.secrets_redacted} REDACTED</Badge>}
                </div>
              </article>
            ))}
          </div>
        ) : response ? (
          <div className="snapshot-grid">
            <div><span>Latency</span><strong>{formatMs(response.latency_ms)}</strong></div>
            <div><span>BM25 Hits</span><strong>{formatNumber(response.bm25_hits)}</strong></div>
            <div><span>Secrets Redacted</span><strong className={secrets ? 'text-rose' : 'text-emerald'}>{secrets}</strong></div>
            <div><span>Packed Tokens</span><strong>{formatNumber(response.packed_tokens)}</strong></div>
            <div><span>Grep Estimate</span><strong>{formatNumber(response.grep_estimated_tokens)}</strong></div>
            <div><span>Packed Fragments</span><strong>{formatNumber(response.packed_context.length)}</strong></div>
          </div>
        ) : (
          <EmptyState title="No retrieval snapshot" detail="Run a search or choose Find Related on a result." />
        )}
      </Panel>
    </aside>
  );
}

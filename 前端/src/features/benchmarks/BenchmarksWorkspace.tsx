import { useEffect, useRef, useState } from 'react';
import { api, SEARCH_MODES } from '../../api/client';
import type {
  AuditResponse,
  BenchmarkMetrics,
  BenchmarkQuery,
  BenchmarkResponse,
  RepoSummary,
  SearchMode,
} from '../../api/types';
import { Badge, cx, EmptyState, ErrorState, Icon, LoadingState, Panel } from '../../components/ui';
import { errorMessage, formatMs, formatNumber } from '../../lib/format';

const modeLabels: Record<SearchMode, string> = {
  enhanced: 'Enhanced',
  baseline: 'Baseline',
  semantic: 'Semantic',
  bm25: 'BM25',
};

type MetricKey = keyof BenchmarkMetrics;
const metricDefinitions: Array<{
  key: MetricKey;
  label: string;
  shortLabel: string;
  format: (value: number) => string;
  lowerIsBetter?: boolean;
}> = [
  { key: 'ndcg_at_10', label: 'NDCG@10', shortLabel: 'NDCG', format: (value) => value.toFixed(3) },
  { key: 'mrr_at_10', label: 'MRR@10', shortLabel: 'MRR', format: (value) => value.toFixed(3) },
  { key: 'recall_at_5', label: 'Recall@5', shortLabel: 'Recall', format: (value) => value.toFixed(3) },
  { key: 'p95_latency_ms', label: 'P95 Latency (ms)', shortLabel: 'P95', format: (value) => formatMs(value), lowerIsBetter: true },
  { key: 'avg_token_savings_pct', label: 'Avg Token Savings (%)', shortLabel: 'Savings', format: (value) => `${value.toFixed(1)}%` },
];

function winnerForQuery(query: BenchmarkQuery): SearchMode {
  return SEARCH_MODES.reduce((winner, mode) => {
    const candidate = query.modes[mode];
    const current = query.modes[winner];
    const candidateScore = candidate.ndcg_at_10 * 100 + candidate.mrr_at_10 * 10 + candidate.recall_at_5;
    const currentScore = current.ndcg_at_10 * 100 + current.mrr_at_10 * 10 + current.recall_at_5;
    return candidateScore > currentScore ? mode : winner;
  }, 'enhanced');
}

function BenchmarkReport({ data }: { data: BenchmarkResponse }) {
  return (
    <div className="benchmark-report">
      <div className="benchmark-kpis">
        {metricDefinitions.map((definition) => {
          const enhanced = data.metrics.enhanced[definition.key];
          const baseline = data.metrics.baseline[definition.key];
          const delta = enhanced - baseline;
          const improved = definition.lowerIsBetter ? delta < 0 : delta > 0;
          const deltaText = definition.key === 'avg_token_savings_pct'
            ? `${delta >= 0 ? '+' : ''}${delta.toFixed(1)} pts`
            : definition.key === 'p95_latency_ms'
              ? `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}ms`
              : `${delta >= 0 ? '+' : ''}${delta.toFixed(3)}`;
          return (
            <article className="benchmark-kpi" key={definition.key}>
              <span>{definition.label}</span>
              <strong>{definition.format(enhanced)}</strong>
              <div>
                <Badge tone={improved ? 'emerald' : delta === 0 ? 'neutral' : 'rose'}>{deltaText}</Badge>
                <span>vs Baseline</span>
              </div>
            </article>
          );
        })}
      </div>

      <section className="mode-comparison">
        <div className="mode-comparison__header">
          <h3>RETRIEVAL MODE COMPARISON</h3>
          <div>{SEARCH_MODES.map((mode) => <span key={mode}><i className={`legend-dot legend-dot--${mode}`} />{modeLabels[mode]}</span>)}</div>
        </div>
        <div className="metric-groups">
          {metricDefinitions.map((definition) => {
            const values = SEARCH_MODES.map((mode) => data.metrics[mode][definition.key]);
            const max = Math.max(...values, 0.000001);
            return (
              <div className="metric-group" key={definition.key}>
                <div className="metric-group__title"><span>{definition.label}</span><Badge tone="blue">ENHANCED {definition.format(data.metrics.enhanced[definition.key])}</Badge></div>
                <div className="metric-group__bars">
                  {SEARCH_MODES.map((mode) => {
                    const value = data.metrics[mode][definition.key];
                    return (
                      <div className="metric-bar" key={mode}>
                        <span>{modeLabels[mode]}</span>
                        <div><i className={`metric-bar__fill metric-bar__fill--${mode}`} style={{ width: `${(value / max) * 100}%` }} /></div>
                        <strong>{definition.format(value)}</strong>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="benchmark-queries">
        <div className="benchmark-queries__header">
          <h3>PER-QUERY ABLATION</h3>
          <span>{data.query_count} ANNOTATED QUERIES · N / M / R = NDCG / MRR / RECALL</span>
        </div>
        {data.queries.length === 0 ? (
          <EmptyState title="No benchmark queries" detail="The backend returned no relevance annotations for this suite." />
        ) : (
          <div className="benchmark-table-wrap">
            <table className="benchmark-table">
              <thead>
                <tr>
                  <th>Benchmark Query</th>
                  {SEARCH_MODES.map((mode) => <th key={mode}>{modeLabels[mode]}</th>)}
                  <th>Winner</th>
                </tr>
              </thead>
              <tbody>
                {data.queries.map((query) => {
                  const winner = winnerForQuery(query);
                  return (
                    <tr key={`${query.repo_id}-${query.category}-${query.query}`}>
                      <td>
                        <strong>{query.query}</strong>
                        <div><Badge>{query.category}</Badge><span>{query.repo_id}</span><span>{query.relevant_chunk_ids.length} relevant</span></div>
                      </td>
                      {SEARCH_MODES.map((mode) => {
                        const metrics = query.modes[mode];
                        return (
                          <td className={cx('benchmark-mode-cell', winner === mode && `benchmark-mode-cell--${mode}`)} key={mode}>
                            <strong>N {metrics.ndcg_at_10.toFixed(3)} · M {metrics.mrr_at_10.toFixed(3)} · R {metrics.recall_at_5.toFixed(3)}</strong>
                            <span>{formatMs(metrics.latency_ms)} · {metrics.token_savings_pct.toFixed(1)}% saved · {metrics.bm25_hits} hits</span>
                          </td>
                        );
                      })}
                      <td><Badge tone={winner === 'enhanced' ? 'blue' : winner === 'semantic' ? 'purple' : winner === 'bm25' ? 'amber' : 'neutral'}>{modeLabels[winner]} leads</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export function BenchmarksWorkspace({ repos }: { repos: RepoSummary[] }) {
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const [scope, setScope] = useState('');
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditRevision, setAuditRevision] = useState(0);
  const auditRequestRef = useRef(0);

  async function runBenchmark() {
    setBenchmarkLoading(true);
    setBenchmarkError(null);
    try {
      setBenchmark(await api.benchmarks());
    } catch (error) {
      setBenchmarkError(errorMessage(error));
    } finally {
      setBenchmarkLoading(false);
    }
  }

  useEffect(() => {
    const requestId = ++auditRequestRef.current;
    setAuditLoading(true);
    setAuditError(null);
    setAudit(null);
    const request = scope ? api.audit(scope) : api.audit();
    request
      .then((data) => {
        if (requestId === auditRequestRef.current) setAudit(data);
      })
      .catch((error: unknown) => {
        if (requestId === auditRequestRef.current) setAuditError(errorMessage(error));
      })
      .finally(() => {
        if (requestId === auditRequestRef.current) setAuditLoading(false);
      });
  }, [scope, auditRevision]);

  const highSeverity = audit
    ? Object.entries(audit.by_severity).reduce((sum, [severity, count]) => sum + (/high|critical/i.test(severity) ? count : 0), 0)
    : 0;

  return (
    <div className="benchmarks-page workspace-page">
      <section className="workspace-intro">
        <div>
          <span className="workspace-intro__eyebrow"><Icon name="activity" size={14} /> MEASURE, ABLATE, VERIFY</span>
          <h1>Benchmarks & Audit</h1>
          <p>Offline relevance annotations, retrieval-mode ablations, latency, context efficiency, and sanitized credential findings.</p>
        </div>
        <Badge tone="emerald"><Icon name="shield" size={11} /> REDACTED OUTPUT ONLY</Badge>
      </section>

      <Panel
        className="benchmark-runner"
        title="IR ABLATION & TOKEN BENCHMARK RUNNER"
        action={
          <button className="primary-button" disabled={benchmarkLoading} onClick={() => void runBenchmark()} type="button">
            <Icon name={benchmarkLoading ? 'activity' : 'play'} size={13} />
            {benchmarkLoading ? 'Running Suite…' : 'Run Offline Benchmark Suite'}
          </button>
        }
      >
        <div className="benchmark-runner__body">
          {benchmarkError && <ErrorState message={benchmarkError} onRetry={() => void runBenchmark()} />}
          {benchmarkLoading && <LoadingState label="Measuring all retrieval modes against relevance annotations" />}
          {!benchmarkLoading && !benchmark && !benchmarkError && (
            <EmptyState title="No benchmark run yet" detail="Run the offline suite to compare Enhanced, Baseline, Semantic, and BM25 on identical annotated queries." />
          )}
          {benchmark && !benchmarkLoading && <BenchmarkReport data={benchmark} />}
        </div>
      </Panel>

      <Panel
        className="audit-panel"
        title="SECURITY & SECRET REDACTION AUDIT"
        action={
          <div className="audit-actions">
            <select aria-label="Audit repository scope" onChange={(event) => setScope(event.target.value)} value={scope}>
              <option value="">All indexed repositories</option>
              {repos.map((repo) => <option key={repo.repo_id} value={repo.repo_id}>{repo.name}</option>)}
            </select>
            <button aria-label="Refresh security audit" className="secondary-button" onClick={() => setAuditRevision((current) => current + 1)} type="button">
              <Icon name="refresh" size={12} />
            </button>
          </div>
        }
      >
        <div className="audit-panel__body">
          {auditLoading ? (
            <LoadingState label="Loading sanitized credential findings" />
          ) : auditError ? (
            <ErrorState message={auditError} onRetry={() => setAuditRevision((current) => current + 1)} />
          ) : audit ? (
            <>
              <div className="audit-kpis">
                <div><span>Total Findings</span><strong className={audit.total_findings ? 'text-rose' : 'text-emerald'}>{formatNumber(audit.total_findings)}</strong></div>
                <div><span>Files Affected</span><strong>{formatNumber(audit.files_affected)}</strong></div>
                <div><span>Credential Rules</span><strong>{formatNumber(Object.keys(audit.by_rule).length)}</strong></div>
                <div><span>High / Critical</span><strong className={highSeverity ? 'text-rose' : 'text-emerald'}>{formatNumber(highSeverity)}</strong></div>
              </div>
              <div className="audit-rule-strip">
                <span>FINDINGS BY RULE</span>
                {Object.keys(audit.by_rule).length === 0 ? <Badge tone="emerald">NO RULES TRIGGERED</Badge> : Object.entries(audit.by_rule).map(([rule, count]) => <Badge key={rule} tone="rose">{rule} · {count}</Badge>)}
              </div>
              {audit.findings.length === 0 ? (
                <EmptyState title="No credential findings" detail="The selected repository scope has no sanitized findings in the current index." />
              ) : (
                <div className="audit-table-wrap">
                  <table className="audit-table">
                    <thead><tr><th>File</th><th>Line</th><th>Credential Type</th><th>Severity</th><th>Redacted Preview</th></tr></thead>
                    <tbody>
                      {audit.findings.map((finding, index) => (
                        <tr key={`${finding.file_path}-${finding.line}-${finding.rule}-${index}`}>
                          <td><Icon name="lock" size={11} /><span>{finding.file_path}</span></td>
                          <td>L{finding.line}</td>
                          <td><Badge tone="rose">{finding.rule}</Badge></td>
                          <td><Badge tone={/high|critical/i.test(finding.severity) ? 'rose' : 'amber'}>{finding.severity.toUpperCase()}</Badge></td>
                          <td><code>{finding.redacted_preview}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

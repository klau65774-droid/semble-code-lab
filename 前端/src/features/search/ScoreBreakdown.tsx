import type { ExplainedSearchResult } from '../../api/types';
import { clamp, formatScore } from '../../lib/format';
import { Badge, cx } from '../../components/ui';

export function ScoreWaterfall({ result }: { result: ExplainedSearchResult }) {
  const { breakdown } = result;
  const dense = breakdown.semantic_rrf * breakdown.alpha_weight;
  const bm25 = breakdown.bm25_rrf * (1 - breakdown.alpha_weight);
  const boost = breakdown.query_boost + breakdown.multi_chunk_boost;
  const total = Math.max(dense + bm25 + boost, 0.000001);
  const segments = [
    { key: 'dense', label: 'Dense', value: dense, className: 'waterfall__segment--dense' },
    { key: 'bm25', label: 'BM25', value: bm25, className: 'waterfall__segment--bm25' },
    { key: 'boost', label: 'Symbol Boost', value: boost, className: 'waterfall__segment--boost' },
  ];

  return (
    <div className="waterfall-wrap">
      <div className="waterfall-caption">
        <span>Score Breakdown Waterfall Bar</span>
        <span>{result.estimated_tokens} tokens</span>
      </div>
      <div className="waterfall" aria-label={`Score breakdown, final score ${formatScore(breakdown.final_score)}`}>
        {segments.map((segment) => (
          <div
            className={cx('waterfall__segment', segment.className)}
            key={segment.key}
            style={{ width: `${Math.max(segment.value > 0 ? 5 : 0, (segment.value / total) * 82)}%` }}
            title={`${segment.label}: ${formatScore(segment.value)}`}
          >
            <span>{segment.label}</span>
            <strong>{segment.key === 'boost' && segment.value > 0 ? '+' : ''}{formatScore(segment.value)}</strong>
          </div>
        ))}
        <div
          className={cx('waterfall__segment waterfall__segment--path', breakdown.path_penalty < 1 && 'waterfall__segment--penalty')}
          title={`Path penalty multiplier: ${breakdown.path_penalty.toFixed(2)}x`}
        >
          <span>Path</span>
          <strong>{breakdown.path_penalty.toFixed(1)}x</strong>
        </div>
        <span className="waterfall__equals">=</span>
        <strong className="waterfall__final">{formatScore(breakdown.final_score)}</strong>
      </div>
    </div>
  );
}

function DecompositionRow({
  label,
  value,
  display,
  color,
  max = 1,
}: {
  label: string;
  value: number;
  display?: string;
  color: string;
  max?: number;
}) {
  return (
    <div className="decomposition-row">
      <span>{label}</span>
      <div className="decomposition-row__track">
        <span className={`decomposition-row__bar decomposition-row__bar--${color}`} style={{ width: `${clamp(Math.abs(value) / max) * 100}%` }} />
      </div>
      <strong>{display ?? formatScore(value)}</strong>
    </div>
  );
}

export function ScoreDecomposition({ result }: { result: ExplainedSearchResult }) {
  const { breakdown } = result;
  return (
    <div className="decomposition">
      <DecompositionRow color="purple" label="Dense raw" value={breakdown.semantic_raw} />
      <DecompositionRow color="purple" label="Dense RRF" value={breakdown.semantic_rrf} max={0.05} />
      <DecompositionRow color="amber" label="BM25 raw" value={breakdown.bm25_raw} display={breakdown.bm25_raw.toFixed(2)} max={Math.max(10, breakdown.bm25_raw)} />
      <DecompositionRow color="amber" label="BM25 RRF" value={breakdown.bm25_rrf} max={0.05} />
      <DecompositionRow color="cyan" label="Symbol Boost" value={breakdown.query_boost} display={`+${formatScore(breakdown.query_boost)}`} max={0.05} />
      {breakdown.boost_reasons.length > 0 && (
        <div className="boost-reasons">
          {breakdown.boost_reasons.map((reason) => <Badge key={reason} tone="cyan">{reason}</Badge>)}
        </div>
      )}
      <DecompositionRow color="emerald" label="Multi-Chunk Coherence" value={breakdown.multi_chunk_boost} max={0.05} />
      <DecompositionRow color={breakdown.path_penalty < 1 ? 'rose' : 'slate'} label="Path Penalty" value={breakdown.path_penalty} display={`${breakdown.path_penalty.toFixed(2)}x`} />
      <DecompositionRow color="slate" label="Saturation Decay" value={breakdown.saturation_decay} display={`${breakdown.saturation_decay.toFixed(2)}x`} />
      <div className="decomposition__total">
        <span>Fused RRF · α {breakdown.alpha_weight.toFixed(2)}</span>
        <strong>{formatScore(breakdown.fused_rrf)}</strong>
      </div>
    </div>
  );
}

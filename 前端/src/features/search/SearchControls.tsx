import type { SearchMode, SearchResponse } from '../../api/types';
import { clamp, formatNumber, formatPercent } from '../../lib/format';
import { Badge, cx, Toggle } from '../../components/ui';

export interface SearchSettings {
  mode: SearchMode;
  compareBaseline: boolean;
  alphaAuto: boolean;
  alpha: number;
  tokenBudget: number;
  tokenUnlimited: boolean;
  rerank: boolean;
  redactSecrets: boolean;
}

export const DEFAULT_SEARCH_SETTINGS: SearchSettings = {
  mode: 'enhanced',
  compareBaseline: true,
  alphaAuto: true,
  alpha: 0.4,
  tokenBudget: 2000,
  tokenUnlimited: false,
  rerank: true,
  redactSecrets: true,
};

export const PRESET_QUERIES = [
  { id: 'semantic', label: 'EN Semantic', repoId: 'semble-core', query: 'hybrid search RRF fusion semantic and BM25' },
  { id: 'embedded', label: 'Embedded snake_case', repoId: 'semble-core', query: 'where is enrich_for_bm25 defined' },
  { id: 'cjk', label: 'Bilingual CJK', repoId: 'semble-core', query: '混合检索和重排序打分逻辑' },
  { id: 'secret', label: 'Secret Audit', repoId: 'bilingual-demo', query: 'database connection credentials 中文业务代码' },
] as const;

const modeLabels: Record<SearchMode, string> = {
  enhanced: 'Enhanced',
  baseline: 'Baseline',
  semantic: 'Semantic',
  bm25: 'BM25',
};

export function SearchControls({
  settings,
  response,
  activeRepoId,
  availableRepoIds,
  onSettingsChange,
  onPreset,
}: {
  settings: SearchSettings;
  response: SearchResponse | null;
  activeRepoId: string;
  availableRepoIds: string[];
  onSettingsChange: (patch: Partial<SearchSettings>) => void;
  onPreset: (preset: (typeof PRESET_QUERIES)[number]) => void;
}) {
  const effectiveAlpha = settings.alphaAuto ? response?.alpha_used ?? settings.alpha : settings.alpha;
  const savings = response?.savings_pct ?? null;

  return (
    <aside className="search-controls">
      <section className="control-section">
        <h2 className="section-label">Preset Queries</h2>
        <div className="preset-grid">
          {PRESET_QUERIES.map((preset) => {
            const active = activeRepoId === preset.repoId && response?.query === preset.query;
            return (
              <button
                className={cx('preset-button', active && 'preset-button--active')}
                disabled={!availableRepoIds.includes(preset.repoId)}
                key={preset.id}
                onClick={() => onPreset(preset)}
                title={`${preset.repoId}: ${preset.query}`}
                type="button"
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="control-section">
        <h2 className="section-label">Mode</h2>
        <div className="mode-grid">
          {(Object.keys(modeLabels) as SearchMode[]).map((mode) => (
            <button
              className={cx('mode-button', settings.mode === mode && 'mode-button--active')}
              key={mode}
              onClick={() => onSettingsChange({ mode })}
              type="button"
            >
              {modeLabels[mode]}
            </button>
          ))}
        </div>
      </section>

      <section className="control-section control-section--stack">
        <div className="control-row">
          <span>Compare Baseline A/B</span>
          <Toggle checked={settings.compareBaseline} label="Compare Baseline A/B" onChange={(compareBaseline) => onSettingsChange({ compareBaseline })} />
        </div>

        <div className="slider-control">
          <div className="control-row">
            <label htmlFor="alpha-fusion">Alpha Fusion <span className="text-muted">({settings.alphaAuto ? `Auto ${effectiveAlpha.toFixed(2)}` : 'Manual'})</span></label>
            <button
              aria-pressed={settings.alphaAuto}
              className={cx('mini-toggle', settings.alphaAuto && 'mini-toggle--active')}
              onClick={() => onSettingsChange(settings.alphaAuto ? { alphaAuto: false, alpha: effectiveAlpha } : { alphaAuto: true })}
              type="button"
            >
              Auto
            </button>
          </div>
          <div className="slider-control__value">{Math.round(effectiveAlpha * 100)}%</div>
          <input
            aria-label="Alpha fusion"
            disabled={settings.alphaAuto}
            id="alpha-fusion"
            max="1"
            min="0"
            onChange={(event) => onSettingsChange({ alpha: Number(event.target.value) })}
            step="0.01"
            type="range"
            value={effectiveAlpha}
          />
          <div className="slider-control__labels"><span>BM25</span><span>Dense</span></div>
        </div>

        <div className="slider-control">
          <div className="control-row">
            <label htmlFor="token-budget">Token Budget</label>
            <button
              aria-pressed={settings.tokenUnlimited}
              className={cx('mini-toggle', settings.tokenUnlimited && 'mini-toggle--active')}
              onClick={() => onSettingsChange({ tokenUnlimited: !settings.tokenUnlimited })}
              type="button"
            >
              Unlimited
            </button>
          </div>
          <div className="slider-control__value">{settings.tokenUnlimited ? 'No limit' : `${formatNumber(settings.tokenBudget)} tok`}</div>
          <input
            aria-label="Token budget"
            disabled={settings.tokenUnlimited}
            id="token-budget"
            max="8000"
            min="500"
            onChange={(event) => onSettingsChange({ tokenBudget: Number(event.target.value) })}
            step="100"
            type="range"
            value={settings.tokenBudget}
          />
          <div className="slider-control__labels"><span>500</span><span>8,000</span></div>
        </div>

        <div className="control-row">
          <span>Rerank</span>
          <Toggle checked={settings.rerank} label="Rerank" onChange={(rerank) => onSettingsChange({ rerank })} />
        </div>
        <div className="control-row">
          <span title="The backend masks recognized credentials for either flag value.">Redact Secrets</span>
          <Toggle checked={settings.redactSecrets} label="Redact Secrets" onChange={(redactSecrets) => onSettingsChange({ redactSecrets })} />
        </div>
      </section>

      <section className="savings-card">
        <div className="savings-card__header">
          <h2>Token Savings</h2>
          <Badge tone="emerald">CONTEXT PACK</Badge>
        </div>
        <strong className="savings-card__value">{formatPercent(savings)}</strong>
        <div className="savings-card__track" aria-label={savings == null ? 'Token savings unavailable' : `${savings.toFixed(1)} percent saved`}>
          <span style={{ width: `${clamp((savings ?? 0) / 100) * 100}%` }} />
        </div>
        <div className="savings-card__detail">
          <span>{formatNumber(response?.packed_tokens)} packed</span>
          <span>/ {formatNumber(response?.full_file_tokens)} full-file tokens</span>
        </div>
      </section>
    </aside>
  );
}

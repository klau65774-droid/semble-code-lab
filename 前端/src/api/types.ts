export type SearchMode = 'enhanced' | 'baseline' | 'semantic' | 'bm25';
export type QueryType = 'symbol' | 'embedded_symbol' | 'natural_language';
export type ContentType = 'code' | 'docs' | 'config';

export interface Health {
  status: 'ok';
  model: string;
  loaded_repos: string[];
  uptime_ms: number;
}

export interface RepoSummary {
  repo_id: string;
  name: string;
  path: string;
  indexed_files: number;
  total_chunks: number;
  languages: Record<string, number>;
  index_ms: number;
  content_types: ContentType[];
}

export interface IndexRequest {
  path: string;
  repo_id?: string | null;
  content_types?: ContentType[] | null;
  force_rebuild?: boolean;
}

export interface SearchRequest {
  repo_id: string;
  query: string;
  top_k?: number;
  mode?: SearchMode;
  alpha?: number | null;
  rerank?: boolean;
  token_budget?: number | null;
  redact_secrets?: boolean;
  compare_baseline?: boolean;
  filter_languages?: string[] | null;
}

export interface RelatedRequest {
  repo_id: string;
  file_path: string;
  line: number;
  top_k?: number;
}

export interface Chunk {
  content: string;
  file_path: string;
  start_line: number;
  end_line: number;
  language?: string | null;
}

export interface ScoreBreakdown {
  semantic_raw: number;
  semantic_rank: number | null;
  semantic_rrf: number;
  bm25_raw: number;
  bm25_rank: number | null;
  bm25_rrf: number;
  alpha_weight: number;
  fused_rrf: number;
  multi_chunk_boost: number;
  query_boost: number;
  boost_reasons: string[];
  path_penalty: number;
  saturation_decay: number;
  final_score: number;
}

export interface ExplainedSearchResult {
  chunk: Chunk;
  chunk_id: string;
  rank: number;
  score: number;
  breakdown: ScoreBreakdown;
  estimated_tokens: number;
  redacted_content: string;
  secrets_redacted: number;
}

export interface ContextFragment {
  file_path: string;
  start_line: number;
  end_line: number;
  content: string;
  estimated_tokens: number;
}

export interface RankDelta {
  chunk_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  baseline_rank: number | null;
  primary_rank: number | null;
  rank_delta: number | null;
}

export interface SearchPayload {
  query: string;
  mode: SearchMode;
  query_type: QueryType;
  tokens: string[];
  detected_symbols: string[];
  alpha_used: number;
  latency_ms: number;
  results: ExplainedSearchResult[];
  packed_tokens: number;
  full_file_tokens: number | null;
  savings_pct: number | null;
  grep_estimated_tokens: number | null;
  bm25_hits: number;
  packed_context: ContextFragment[];
}

export interface BaselineComparison extends SearchPayload {
  rank_deltas: RankDelta[];
}

export interface SearchResponse extends SearchPayload {
  baseline_comparison: BaselineComparison | null;
}

export interface FileSummary {
  file_path: string;
  language: string | null;
  chunk_count: number;
  total_lines: number;
  estimated_tokens: number;
  path_penalty: number;
  secrets_detected: number;
}

export interface IndexedChunk {
  chunk_id: string;
  start_line: number;
  end_line: number;
  content: string;
  estimated_tokens: number;
  bm25_tokens_preview: string[];
  secrets_redacted: number;
}

export interface FileChunks {
  file_path: string;
  total_lines: number;
  chunks: IndexedChunk[];
}

export interface RelatedResult {
  chunk_id: string;
  chunk: Chunk;
  score: number;
  estimated_tokens: number;
  secrets_redacted: number;
}

export interface RelatedResponse {
  repo_id: string;
  file_path: string;
  line: number;
  results: RelatedResult[];
}

export interface BenchmarkMetrics {
  ndcg_at_10: number;
  mrr_at_10: number;
  recall_at_5: number;
  p95_latency_ms: number;
  avg_token_savings_pct: number;
}

export interface BenchmarkQueryMetrics {
  ndcg_at_10: number;
  mrr_at_10: number;
  recall_at_5: number;
  latency_ms: number;
  token_savings_pct: number;
  ranked_chunk_ids: string[];
  bm25_hits: number;
}

export interface BenchmarkQuery {
  repo_id: string;
  category: string;
  query: string;
  relevant_chunk_ids: string[];
  modes: Record<SearchMode, BenchmarkQueryMetrics>;
}

export interface BenchmarkResponse {
  query_count: number;
  metrics: Record<SearchMode, BenchmarkMetrics>;
  queries: BenchmarkQuery[];
}

export interface AuditFinding {
  file_path: string;
  line: number;
  rule: string;
  severity: string;
  redacted_preview: string;
}

export interface AuditResponse {
  total_findings: number;
  files_affected: number;
  by_rule: Record<string, number>;
  by_severity: Record<string, number>;
  findings: AuditFinding[];
}

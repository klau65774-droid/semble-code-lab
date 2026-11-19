import type {
  AuditResponse,
  BenchmarkResponse,
  FileChunks,
  FileSummary,
  Health,
  RelatedResponse,
  RepoSummary,
  SearchResponse,
} from '../api/types';

export const repos: RepoSummary[] = [
  {
    repo_id: 'semble-core',
    name: 'semble-core',
    path: 'D:/workspace/semble-core',
    indexed_files: 29,
    total_chunks: 320,
    languages: { python: 24, markdown: 5 },
    index_ms: 1240,
    content_types: ['code', 'docs'],
  },
  {
    repo_id: 'bilingual-demo',
    name: 'bilingual-demo',
    path: 'D:/workspace/bilingual-demo',
    indexed_files: 8,
    total_chunks: 46,
    languages: { python: 6, typescript: 2 },
    index_ms: 420,
    content_types: ['code', 'docs', 'config'],
  },
];

export const health: Health = {
  status: 'ok',
  model: 'BAAI/bge-small-en-v1.5',
  loaded_repos: ['semble-core', 'bilingual-demo'],
  uptime_ms: 98342,
};

export const searchResponse: SearchResponse = {
  query: 'where is enrich_for_bm25 defined',
  mode: 'enhanced',
  query_type: 'embedded_symbol',
  tokens: ['where', 'enrich_for_bm25', 'defined'],
  detected_symbols: ['enrich_for_bm25'],
  alpha_used: 0.4,
  latency_ms: 1.3,
  packed_tokens: 1420,
  full_file_tokens: 16500,
  savings_pct: 91.4,
  grep_estimated_tokens: 4800,
  bm25_hits: 12,
  packed_context: [],
  results: [
    {
      chunk: {
        content: 'def enrich_for_bm25(chunk):\n    password = "PLAINTEXT_MUST_NOT_RENDER"',
        file_path: 'semble/index/sparse.py',
        start_line: 18,
        end_line: 21,
        language: 'python',
      },
      chunk_id: 'sparse.py:18-29',
      rank: 1,
      score: 0.051,
      estimated_tokens: 86,
      redacted_content:
        'def enrich_for_bm25(chunk: Chunk) -> str:\n    """Prepend symbol and file tokens for lexical indexing."""\n    tokens = [chunk.symbol_name, chunk.file_path]\n    password = "[REDACTED]"',
      secrets_redacted: 1,
      breakdown: {
        semantic_raw: 0.82,
        semantic_rank: 2,
        semantic_rrf: 0.02,
        bm25_raw: 8.4,
        bm25_rank: 1,
        bm25_rrf: 0.0267,
        alpha_weight: 0.4,
        fused_rrf: 0.024,
        multi_chunk_boost: 0.006,
        query_boost: 0.021,
        boost_reasons: ['exact symbol: enrich_for_bm25', 'definition match'],
        path_penalty: 1,
        saturation_decay: 1,
        final_score: 0.051,
      },
    },
    {
      chunk: {
        content: 'sparse_text = enrich_for_bm25(chunk)',
        file_path: 'semble/index/create.py',
        start_line: 63,
        end_line: 70,
        language: 'python',
      },
      chunk_id: 'create.py:63-70',
      rank: 2,
      score: 0.024,
      estimated_tokens: 64,
      redacted_content:
        'sparse_text = enrich_for_bm25(chunk)\nbm25_corpus.append(tokenize(sparse_text))',
      secrets_redacted: 0,
      breakdown: {
        semantic_raw: 0.72,
        semantic_rank: 1,
        semantic_rrf: 0.0275,
        bm25_raw: 5.2,
        bm25_rank: 3,
        bm25_rrf: 0.015,
        alpha_weight: 0.4,
        fused_rrf: 0.02,
        multi_chunk_boost: 0,
        query_boost: 0.004,
        boost_reasons: ['symbol reference'],
        path_penalty: 1,
        saturation_decay: 1,
        final_score: 0.024,
      },
    },
  ],
  baseline_comparison: {
    query: 'where is enrich_for_bm25 defined',
    mode: 'baseline',
    query_type: 'embedded_symbol',
    tokens: ['where', 'enrich_for_bm25', 'defined'],
    detected_symbols: ['enrich_for_bm25'],
    alpha_used: 0.4,
    latency_ms: 0.8,
    packed_tokens: 1480,
    full_file_tokens: 16500,
    savings_pct: 91,
    grep_estimated_tokens: 4800,
    bm25_hits: 12,
    packed_context: [],
    results: [],
    rank_deltas: [
      {
        chunk_id: 'sparse.py:18-29',
        file_path: 'semble/index/sparse.py',
        start_line: 18,
        end_line: 29,
        baseline_rank: 3,
        primary_rank: 1,
        rank_delta: 2,
      },
      {
        chunk_id: 'create.py:63-70',
        file_path: 'semble/index/create.py',
        start_line: 63,
        end_line: 70,
        baseline_rank: 1,
        primary_rank: 2,
        rank_delta: -1,
      },
    ],
  },
};

export const relatedResponse: RelatedResponse = {
  repo_id: 'semble-core',
  file_path: 'semble/index/sparse.py',
  line: 18,
  results: [
    {
      chunk_id: 'fusion.py:44-61',
      chunk: {
        content: 'def fuse_rankings(): pass',
        file_path: 'semble/index/fusion.py',
        start_line: 44,
        end_line: 61,
        language: 'python',
      },
      score: 0.87,
      estimated_tokens: 112,
      secrets_redacted: 0,
    },
  ],
};

export const files: FileSummary[] = [
  {
    file_path: 'semble/index/sparse.py',
    language: 'python',
    chunk_count: 14,
    total_lines: 228,
    estimated_tokens: 1840,
    path_penalty: 1,
    secrets_detected: 0,
  },
  {
    file_path: 'tests/test_search.py',
    language: 'python',
    chunk_count: 8,
    total_lines: 140,
    estimated_tokens: 980,
    path_penalty: 0.3,
    secrets_detected: 2,
  },
];

export const fileChunks: FileChunks = {
  file_path: 'semble/index/sparse.py',
  total_lines: 228,
  chunks: [
    {
      chunk_id: 'sparse.py:18-29',
      start_line: 18,
      end_line: 29,
      content: 'def enrich_for_bm25(chunk: Chunk) -> str:\n    return " ".join(tokenize(chunk.content))',
      estimated_tokens: 86,
      bm25_tokens_preview: ['enrich_for_bm25', 'chunk', 'tokenize', 'content'],
      secrets_redacted: 0,
    },
    {
      chunk_id: 'sparse.py:31-48',
      start_line: 31,
      end_line: 48,
      content: 'class BM25Index:\n    pass',
      estimated_tokens: 120,
      bm25_tokens_preview: ['bm25index', 'class', 'index'],
      secrets_redacted: 0,
    },
  ],
};

export const benchmarkResponse: BenchmarkResponse = {
  query_count: 2,
  metrics: {
    enhanced: { ndcg_at_10: 0.89, mrr_at_10: 0.92, recall_at_5: 0.84, p95_latency_ms: 18.2, avg_token_savings_pct: 91.4 },
    baseline: { ndcg_at_10: 0.71, mrr_at_10: 0.74, recall_at_5: 0.7, p95_latency_ms: 8.1, avg_token_savings_pct: 88.2 },
    semantic: { ndcg_at_10: 0.76, mrr_at_10: 0.78, recall_at_5: 0.75, p95_latency_ms: 12.5, avg_token_savings_pct: 90.1 },
    bm25: { ndcg_at_10: 0.68, mrr_at_10: 0.72, recall_at_5: 0.66, p95_latency_ms: 5.4, avg_token_savings_pct: 87.5 },
  },
  queries: [
    {
      repo_id: 'semble-core',
      category: 'embedded_symbol',
      query: 'where is enrich_for_bm25 defined',
      relevant_chunk_ids: ['sparse.py:18-29'],
      modes: {
        enhanced: { ndcg_at_10: 1, mrr_at_10: 1, recall_at_5: 1, latency_ms: 1.3, token_savings_pct: 91.4, ranked_chunk_ids: ['sparse.py:18-29'], bm25_hits: 12 },
        baseline: { ndcg_at_10: 0.63, mrr_at_10: 0.5, recall_at_5: 1, latency_ms: 0.8, token_savings_pct: 89, ranked_chunk_ids: ['create.py:63-70'], bm25_hits: 12 },
        semantic: { ndcg_at_10: 0.8, mrr_at_10: 0.8, recall_at_5: 1, latency_ms: 1.1, token_savings_pct: 90, ranked_chunk_ids: ['sparse.py:18-29'], bm25_hits: 0 },
        bm25: { ndcg_at_10: 0.7, mrr_at_10: 0.7, recall_at_5: 1, latency_ms: 0.5, token_savings_pct: 88, ranked_chunk_ids: ['sparse.py:18-29'], bm25_hits: 12 },
      },
    },
  ],
};

export const auditResponse: AuditResponse = {
  total_findings: 3,
  files_affected: 2,
  by_rule: { AWS: 1, DSN: 2 },
  by_severity: { high: 3 },
  findings: [
    {
      file_path: 'bilingual_demo/config.py',
      line: 12,
      rule: 'DSN',
      severity: 'high',
      redacted_preview: 'DATABASE_URL = "postgresql://[REDACTED]"',
    },
    {
      file_path: 'bilingual_demo/payments.py',
      line: 8,
      rule: 'AWS',
      severity: 'high',
      redacted_preview: 'AWS_ACCESS_KEY_ID = "[REDACTED]"',
    },
  ],
};

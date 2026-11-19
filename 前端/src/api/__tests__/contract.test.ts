import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { API_CONTRACT, CONTENT_TYPES, SEARCH_MODES } from '../client';

const openApi = JSON.parse(
  readFileSync(resolve(process.cwd(), '../后端/docs/openapi.json'), 'utf8'),
) as {
  paths: Record<string, Record<string, unknown>>;
  components: {
    schemas: Record<
      string,
      {
        enum?: string[];
        properties?: Record<string, { enum?: string[] }>;
        required?: string[];
      }
    >;
  };
};

const schemas = openApi.components.schemas;

describe('backend OpenAPI contract', () => {
  it('uses exactly the nine backend endpoint paths and methods', () => {
    expect(Object.keys(openApi.paths).sort()).toEqual(
      Object.values(API_CONTRACT)
        .map((endpoint) => endpoint.path)
        .sort(),
    );

    for (const endpoint of Object.values(API_CONTRACT)) {
      expect(openApi.paths[endpoint.path], endpoint.path).toBeDefined();
      expect(openApi.paths[endpoint.path][endpoint.method], endpoint.path).toBeDefined();
    }
  });

  it('keeps all retrieval modes aligned with SearchRequest', () => {
    expect(schemas.SearchRequest.properties?.mode?.enum).toEqual([...SEARCH_MODES]);
  });

  it('keeps indexing content types aligned with ContentType', () => {
    expect(schemas.ContentType.enum).toEqual([...CONTENT_TYPES]);
  });

  it.each([
    [
      'SearchRequest',
      [
        'repo_id',
        'query',
        'top_k',
        'mode',
        'alpha',
        'rerank',
        'token_budget',
        'redact_secrets',
        'compare_baseline',
        'filter_languages',
      ],
      ['repo_id', 'query'],
    ],
    [
      'IndexRequest',
      ['path', 'repo_id', 'content_types', 'force_rebuild'],
      ['path'],
    ],
    [
      'RelatedRequest',
      ['repo_id', 'file_path', 'line', 'top_k'],
      ['repo_id', 'file_path', 'line'],
    ],
  ] as const)('matches %s fields without drift', (schemaName, properties, required) => {
    expect(Object.keys(schemas[schemaName].properties ?? {}).sort()).toEqual(
      [...properties].sort(),
    );
    expect([...(schemas[schemaName].required ?? [])].sort()).toEqual([...required].sort());
  });
});

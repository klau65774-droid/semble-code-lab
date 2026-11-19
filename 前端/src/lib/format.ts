export function formatNumber(value: number | null | undefined): string {
  return value == null ? '—' : new Intl.NumberFormat('en-US').format(value);
}

export function formatMs(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${value < 10 ? value.toFixed(1) : value.toFixed(0)}ms`;
}

export function formatPercent(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(1)}%`;
}

export function formatScore(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(3);
}

export function formatRank(value: number | null | undefined): string {
  return value == null ? '—' : `#${value}`;
}

export function baseName(filePath: string): string {
  return filePath.split(/[\\/]/).filter(Boolean).at(-1) ?? filePath;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected request failure';
}

export function clamp(value: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, value));
}

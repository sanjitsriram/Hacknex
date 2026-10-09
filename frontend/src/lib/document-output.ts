import type { DocumentParsingRunResult } from './api';

export function documentOutput(run: DocumentParsingRunResult, format: 'markdown' | 'json'): string {
  if (format === 'markdown') return run.markdown_text || run.pages.map(page => page.markdown_text).join('\n\n');
  return JSON.stringify({ schema_version: '1.0', provenance_layer: 'automated_provider_output', review_status: 'unverified', coordinate_space: 'original_page_percent_xywh', parsing_run: run }, null, 2);
}

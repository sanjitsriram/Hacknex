'use client';

import { useState } from 'react';
import type { DocumentParsingRunResult } from '@/lib/api';
import { documentOutput } from '@/lib/document-output';

import OcrMarkdown from './OcrMarkdown';

export function DocumentOutput({ run, formatOverride }: { run: DocumentParsingRunResult | null, formatOverride?: 'markdown' | 'json' }) {
  const [internalFormat, setInternalFormat] = useState<'markdown' | 'json'>('markdown');
  const format = formatOverride || internalFormat;
  const [message, setMessage] = useState('');
  const output = run ? documentOutput(run, format) : '';
  async function copy() {
    try { await navigator.clipboard.writeText(output); setMessage('Copied to clipboard.'); }
    catch { setMessage('Clipboard unavailable. Use Download instead.'); }
  }
  function download() {
    if (!run) return;
    const url = URL.createObjectURL(new Blob([output], { type: format === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `document-${run.id.replace(/[^a-zA-Z0-9_-]/g, '_')}.${format === 'json' ? 'json' : 'md'}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="document-output" aria-label="Document output">
    {!formatOverride && (
      <div className="output-toolbar">
        <div className="output-formats" aria-label="Output format">{(['markdown', 'json'] as const).map(value => <button key={value} type="button" aria-pressed={format === value} onClick={() => { setInternalFormat(value); setMessage(''); }}>{value === 'json' ? 'JSON' : 'Markdown'}</button>)}</div>
        <div><button type="button" disabled={!output} onClick={copy}>Copy</button><button type="button" disabled={!output} onClick={download}>Download</button></div>
      </div>
    )}
    {formatOverride && (
      <div className="output-toolbar" style={{ justifyContent: 'flex-end' }}>
        <div><button type="button" disabled={!output} onClick={copy}>Copy {format === 'json' ? 'JSON' : 'Markdown'}</button><button type="button" disabled={!output} onClick={download}>Download</button></div>
      </div>
    )}
    <p className="output-caption">{format === 'json' ? 'Structured provider result · all pages, source coordinates and provenance.' : 'Markdown source · all pages · preserved provider text.'} Automated output is unverified.</p>
    <p role="status" className="output-status">{message}</p>
    {run ? (
      format === 'markdown' 
        ? <div style={{ padding: '0 20px 20px', background: '#fff' }}><OcrMarkdown content={output || 'No Markdown returned by the provider.'} /></div>
        : <pre tabIndex={0} className="output-code"><code>{output || 'No JSON returned by the provider.'}</code></pre>
    ) : <p className="empty-state">Run Document Intelligence to generate output.</p>}
  </section>;
}

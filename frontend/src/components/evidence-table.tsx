'use client';

import { useEffect, useState } from 'react';

type Cell = { text: string; heading: boolean; columns: number; rows: number };

// Parse in a detached document; render only cell text through React's escaping.
// Provider markup, URLs, styles, and event handlers never enter the live DOM.
export function EvidenceTable({ content }: { content: string }) {
  const [rows, setRows] = useState<Cell[][]>([]);
  useEffect(() => {
    const parsed = new DOMParser().parseFromString(content, 'text/html');
    parsed.querySelectorAll('script,style,iframe,object,embed').forEach(node => node.remove());
    const table = parsed.querySelector('table');
    const span = (value: string | null) => Math.min(100, Math.max(1, Number.parseInt(value || '1', 10) || 1));
    setRows(table ? Array.from(table.rows).map(row => Array.from(row.cells).map(cell => ({
      text: cell.textContent || '', heading: cell.tagName === 'TH',
      columns: span(cell.getAttribute('colspan')), rows: span(cell.getAttribute('rowspan')),
    }))) : []);
  }, [content]);

  return <div className="evidence-table">
    <p className="evidence-disclaimer">Unverified model output — compare every value with the source.</p>
    {rows.length > 0 ? <div className="evidence-table-scroll" tabIndex={0} role="region" aria-label="Extracted table"><table><tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => cell.heading
      ? <th key={j} colSpan={cell.columns} rowSpan={cell.rows}>{cell.text}</th>
      : <td key={j} colSpan={cell.columns} rowSpan={cell.rows}>{cell.text}</td>)}</tr>)}</tbody></table></div>
      : <pre>{content || 'No table content returned.'}</pre>}
    <details><summary>Raw provider output</summary><pre>{content}</pre></details>
  </div>;
}

import React from 'react';
import { Sparkles, FileText, LayoutDashboard, ScanLine, X, RotateCw } from 'lucide-react';
import { DocumentOutput } from '../document-output';
import { EvidenceTable } from '../evidence-table';

export function ParsePanel({
  vlJobState,
  hasParsingRun,
  parsingRun,
  onCancelDocumentIntelligence,
  onRunDocumentIntelligence,
  jobState,
  onRunFullOcr,
  onCancelFullOcr,
  subTab,
  setSubTab,
  layoutBlocks,
  activeBlockId,
  setActiveBlockId,
}: any) {
  return (
    <div className="parse-panel">
      <details className="processing-controls" open={!hasParsingRun}>
        <summary>Processing tools <span>Multi-Model Options</span></summary>
        
        {/* PaddleOCR-VL Banner */}
        <div className="vl-action-banner" style={{ marginBottom: 12 }}>
          <div className="banner-info">
            <h4><Sparkles size={14} /> Document Intelligence · PaddleOCR-VL-1.6 Cloud</h4>
            <p>
              {vlJobState?.running
                ? `Processing document intelligence pipeline (${vlJobState.stage || 'layout_analysis'}... Status: ${vlJobState.status || 'running'}${typeof vlJobState.elapsedSeconds === 'number' ? ` · ${vlJobState.elapsedSeconds}s elapsed` : ''})`
                : hasParsingRun
                ? `${parsingRun?.total_blocks} layout blocks & ${parsingRun?.pages[0]?.tables_count || 0} tables parsed in ${((parsingRun?.execution_time_ms || 0) / 1000).toFixed(1)}s.`
                : 'Execute hierarchical layout analysis, reading-order prediction, and sanitized Markdown parsing.'}
            </p>
            {vlJobState?.error && (
              <p style={{ color: '#d32f2f', marginTop: 4, fontWeight: 500 }}>
                {vlJobState.error}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {vlJobState?.running && (
              <button type="button" className="button secondary small-button" style={{ minHeight: 38, borderColor: '#e57373', color: '#c62828' }} onClick={onCancelDocumentIntelligence} title="Abort currently running pipeline">
                <X size={13} /><span>Cancel</span>
              </button>
            )}
            <button type="button" className="vl-run-btn" disabled={vlJobState?.running} onClick={() => onRunDocumentIntelligence(false)}>
              {vlJobState?.running ? (
                <><RotateCw size={14} className="loading-spinner" /><span>Analyzing Document...</span></>
              ) : (
                <><Sparkles size={15} /><span>{hasParsingRun ? 'Re-run PaddleOCR-VL' : 'Run Document Intelligence — PaddleOCR-VL'}</span></>
              )}
            </button>
          </div>
        </div>

        {/* PP-OCRv6 Cloud Banner */}
        <div className="vl-action-banner" style={{ border: '1px solid #d0d7de', background: '#f6f8fa' }}>
          <div className="banner-info">
            <h4><ScanLine size={14} /> Text Recognition · PP-OCRv6 Cloud</h4>
            <p>
              {jobState?.running
                ? `Running PP-OCRv6 line recognition (${jobState.stage || 'ocr'}... Status: ${jobState.status || 'running'})`
                : 'Execute robust baseline OCR processing for line-level extraction and accuracy comparisons.'}
            </p>
            {jobState?.error && (
              <p style={{ color: '#d32f2f', marginTop: 4, fontWeight: 500 }}>
                {jobState.error}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {jobState?.running && (
              <button type="button" className="button secondary small-button" style={{ minHeight: 38, borderColor: '#e57373', color: '#c62828' }} onClick={onCancelFullOcr} title="Abort currently running PP-OCRv6 pipeline">
                <X size={13} /><span>Cancel</span>
              </button>
            )}
            <button type="button" className="vl-run-btn" style={{ background: '#24292f' }} disabled={jobState?.running} onClick={() => onRunFullOcr(false)}>
              {jobState?.running ? (
                <><RotateCw size={14} className="loading-spinner" /><span>Running PP-OCRv6...</span></>
              ) : (
                <><ScanLine size={15} /><span>Run PP-OCRv6 Cloud</span></>
              )}
            </button>
          </div>
        </div>
      </details>

      <div className="doc-subnav">
        <button type="button" className={`doc-subnav-btn ${subTab === 'layout' || subTab === 'regions' || subTab === 'tables' || subTab === 'fusion' ? 'active' : ''}`} onClick={() => setSubTab('layout')}>
          <FileText size={13} /><span>Readable View</span>
        </button>
        <button type="button" className={`doc-subnav-btn ${subTab === 'markdown' ? 'active' : ''}`} onClick={() => setSubTab('markdown')}>
          <LayoutDashboard size={13} /><span>Markdown View</span>
        </button>
        <button type="button" className={`doc-subnav-btn ${subTab === 'json' ? 'active' : ''}`} onClick={() => setSubTab('json')}>
          <ScanLine size={13} /><span>JSON View</span>
        </button>
      </div>

      {(subTab === 'layout' || subTab === 'regions' || subTab === 'tables' || subTab === 'fusion') && (
        <div>
          {hasParsingRun ? (
            <div className="region-list">
              {layoutBlocks.map((b: any) => {
                const isSelected = activeBlockId === b.block_id;
                const typeClass = b.block_type === 'paragraph_title' ? 'title-pill' : b.block_type === 'table' ? 'table-pill' : b.block_type === 'formula' ? 'formula-pill' : 'text-pill';

                return (
                  <div
                    key={b.block_id}
                    className={`layout-block-card ${isSelected ? 'focused' : ''}`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setActiveBlockId(b.block_id); } }}
                    onClick={() => setActiveBlockId(b.block_id)}
                  >
                    <div className="layout-block-card-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="block-order-badge" style={{ background: '#edf2ee', color: '#245340' }}>#{b.reading_order}</span>
                        <span className={`type-pill ${typeClass}`}>{b.block_type.replace('_', ' ')}</span>
                      </div>
                    </div>
                    <div className="layout-block-card-content">{b.block_type === 'table' ? <EvidenceTable content={b.content} /> : b.content || 'No text returned'}</div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state">Run Document Intelligence to view the parsed document.</div>
          )}
        </div>
      )}
      {subTab === 'markdown' && <DocumentOutput run={parsingRun} formatOverride="markdown" />}
      {subTab === 'json' && <DocumentOutput run={parsingRun} formatOverride="json" />}
    </div>
  );
}

import React, { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, CheckCircle, Search } from 'lucide-react';

export function ReviewPanel({ hasParsingRun, layoutBlocks, doc, corrections, onResolve, activeBlockId, setActiveBlockId }: any) {
  const [filter, setFilter] = useState('all'); // all, needs_review, verified

  if (!hasParsingRun) {
    return (
      <div className="review-panel">
        <div className="transcript-title">
          <div><span className="eyebrow">EVIDENCE-AWARE SELECTIVE REVIEW</span><p>Human verification based on OCR uncertainty.</p></div>
        </div>
        <div className="empty-state">Run Document Intelligence first to generate a review queue.</div>
      </div>
    );
  }

  const reviewItems = layoutBlocks.map((b: any) => {
    const key = `${doc.id}:${b.block_id}`;
    const confirmed = corrections[key];
    const needsReview = b.confidence !== undefined && b.confidence < 0.9;
    return {
      ...b,
      key,
      confirmed,
      needsReview
    };
  });

  const filteredItems = reviewItems.filter((item: any) => {
    if (filter === 'needs_review') return item.needsReview && !item.confirmed;
    if (filter === 'verified') return !!item.confirmed;
    return true;
  });

  return (
    <div className="review-panel">
      <div className="transcript-title">
        <div><span className="eyebrow">EVIDENCE-AWARE SELECTIVE REVIEW</span><p>Review items flagged for low confidence by PaddleOCR-VL.</p></div>
      </div>

      <div className="doc-subnav">
        <button type="button" className={`doc-subnav-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>
          All Items ({reviewItems.length})
        </button>
        <button type="button" className={`doc-subnav-btn ${filter === 'needs_review' ? 'active' : ''}`} onClick={() => setFilter('needs_review')}>
          Needs Review ({reviewItems.filter((i: any) => i.needsReview && !i.confirmed).length})
        </button>
        <button type="button" className={`doc-subnav-btn ${filter === 'verified' ? 'active' : ''}`} onClick={() => setFilter('verified')}>
          Verified ({reviewItems.filter((i: any) => !!i.confirmed).length})
        </button>
      </div>

      <div className="region-list">
        {filteredItems.map((item: any, idx: number) => {
          const isSelected = activeBlockId === item.block_id;
          return (
            <div className={`region-card ${isSelected ? 'focused' : ''}`} key={item.key}>
              <button className="region-card-title" onClick={() => setActiveBlockId(item.block_id)}>
                <span className={`region-number ${item.confirmed ? 'done' : item.needsReview ? 'amber' : ''}`}>
                  {item.confirmed ? <Check size={13} /> : idx + 1}
                </span>
                <strong>{item.content?.substring(0, 50) || 'Empty block'}</strong>
                <span>
                  {item.confirmed ? 'Verified' : item.needsReview ? 'Low Confidence' : 'Auto-Verified'}
                </span>
                <ChevronDown size={15} />
              </button>

              {isSelected && (
                <div className="region-detail">
                  <p style={{ fontSize: 12, marginBottom: 8 }}>
                    <strong>Reason for flag:</strong> {item.needsReview ? `Model confidence is ${(item.confidence * 100).toFixed(1)}% (< 90%)` : 'None (High confidence)'}
                  </p>
                  <div style={{ background: '#f5faf3', padding: '10px 12px', borderRadius: 5, marginBottom: 10, border: '1px solid #d4ebd0' }}>
                    <span style={{ fontSize: 9, color: '#3c6e3f', fontWeight: 600 }}>PADDLEOCR-VL OUTPUT:</span>
                    <p style={{ margin: '3px 0 0', color: '#204d2e' }}>"{item.content}"</p>
                  </div>
                  
                  <form onSubmit={(e) => {
                    e.preventDefault();
                    const val = (e.target as any).elements.verifyInput.value;
                    onResolve(doc.id, item.block_id, val);
                  }}>
                    <label className="field-label">Reviewer Verified Reading</label>
                    <input 
                      name="verifyInput" 
                      className="text-input" 
                      defaultValue={item.confirmed || item.content} 
                      required 
                    />
                    <div className="decision-actions" style={{ marginTop: 10 }}>
                      <button className="button primary small-button" type="submit">
                        <Check size={14} /> Confirm
                      </button>
                    </div>
                  </form>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

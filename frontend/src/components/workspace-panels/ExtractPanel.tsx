import React, { useState } from 'react';
import { Database, FileJson, Copy, CheckCircle, RotateCw } from 'lucide-react';

export function ExtractPanel({ hasParsingRun, parsingRun, vlJobState }: any) {
  const [template, setTemplate] = useState('lab-report');
  const [extractedData, setExtractedData] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);

  const runExtraction = async () => {
    if (!parsingRun) return;
    setError(null);
    setLoading(true);

    const fullText = parsingRun.pages?.[0]?.blocks?.map((b: any) => b.content).join('\n') || '';

    try {
      let result: any = {};
      if (template === 'lab-report') {
        const response = await fetch('/api/extract/lab-report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(parsingRun)
        });
        
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.error || `HTTP ${response.status} failed to extract`);
        }
        
        result = await response.json();
      } else if (template === 'invoice') {
        result = {
          invoiceNumber: fullText.match(/invoice\s*(?:no|number)?\s*[:#]?\s*([A-Z0-9-]+)/i)?.[1] || null,
          total: fullText.match(/total\s*[:$]?\s*([\d,]+\.\d{2})/i)?.[1] || null,
          date: fullText.match(/\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2}/)?.[0] || null,
        };
      } else if (template === 'application') {
        result = {
          name: fullText.match(/name\s*:\s*([A-Za-z\s]+)/i)?.[1]?.trim() || null,
          signaturePresent: /signature/i.test(fullText),
          date: fullText.match(/\d{2}\/\d{2}\/\d{4}|\d{4}-\d{2}-\d{2}/)?.[0] || null,
        };
      } else {
        result = {
          keysFound: (fullText.match(/[A-Z][a-z]+:/g) || []).length,
          documentLength: fullText.length,
          rawPreview: fullText.substring(0, 100) + '...',
        };
      }
      setExtractedData(result);
    } catch (e: any) {
      setError(e.message || 'Failed to parse Document');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (extractedData) {
      navigator.clipboard.writeText(JSON.stringify(extractedData, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="extract-panel">
      <div className="transcript-title">
        <div><span className="eyebrow">STRUCTURED EXTRACTION</span><p>Schema-driven extraction using verified layout results.</p></div>
      </div>
      
      {!hasParsingRun ? (
        vlJobState?.running ? (
          <div className="empty-state" style={{ padding: 40 }}>
            <Database size={40} style={{ color: '#2b5e39', marginBottom: 16 }} />
            <h3>Processing Document...</h3>
            <p>Running PaddleOCR-VL Document Intelligence pipeline. Extracted data will appear here automatically.</p>
          </div>
        ) : (
          <div className="empty-state">Please select a document or parse it first to extract structured fields.</div>
        )
      ) : (
        <div className="extraction-workspace">
          <div className="template-selector" style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>Select Schema Template:</label>
            <select 
              value={template} 
              onChange={(e) => setTemplate(e.target.value)}
              style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #ccc' }}
            >
              <option value="lab-report">Laboratory Report (Zod Schema)</option>
              <option value="general">General Key-Value Document</option>
              <option value="invoice">Invoice or Receipt</option>
              <option value="application">Handwritten Application / Form</option>
            </select>
          </div>
          
          <button className="button primary" onClick={runExtraction} disabled={loading} style={{ marginBottom: 20 }}>
            {loading ? <><RotateCw size={14} className="loading-spinner" /> Extracting...</> : <><Database size={16} /> Run Extraction</>}
          </button>
          
          {error && <div className="form-error" style={{ marginBottom: 20 }}>{error}</div>}

          {extractedData && (
            <div className="extraction-results">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h4 style={{ margin: 0 }}><FileJson size={16} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> JSON Output</h4>
                <button className="text-button" onClick={handleCopy}>
                  {copied ? <CheckCircle size={14} color="green" /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy JSON'}
                </button>
              </div>
              <pre style={{ background: '#f4f4f4', padding: 12, borderRadius: 4, overflowX: 'auto', fontSize: 13 }}>
                <code>{JSON.stringify(extractedData, null, 2)}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

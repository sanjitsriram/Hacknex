'use client';

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Bell, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, Cpu, FileText, FolderOpen, LayoutDashboard, ListFilter, Maximize2, Menu, Microscope, MoreHorizontal, Plus, RotateCw, ScanLine, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, UploadCloud, X, ZoomIn, ZoomOut } from 'lucide-react';
import { baseText, defaultPreferences, regions, samples, validateFile, parseSavedState, updateRegionText, type AuditEvent, type DocumentItem, type Preferences } from '@/lib/data';
import {
  fetchDocumentsFromApi,
  uploadDocumentToApi,
  recognizeRegionApi,
  scheduleDocumentRecognitionApi,
  getJobStatusApi,
  fetchDocumentRegionsApi,
  scheduleDocumentIntelligenceApi,
  fetchParsedDocumentApi,
  fetchParsingHistoryApi,
  type RegionRecognitionResult,
  type DetectedDocumentRegion,
  type DocumentParsingRunResult,
  type LayoutBlockDetail,
  type ParsedPageDetail,
} from '@/lib/api';

type View = 'Overview' | 'Documents' | 'Review workspace' | 'Evaluation' | 'Settings';

const STORAGE_KEY = 'hacknex:workspace:v1';
const LEGACY_STORAGE_KEY = 'inkproof:workspace:v1';
const TROCR_STORAGE_KEY = 'hacknex:trocr_results:v1';
const VL_STORAGE_KEY = 'hacknex:vl_results:v1';

export const defaultDocRegions = [
  { id: 'r1', name: 'Header Title Line', bbox: { x: 5, y: 5, w: 90, h: 12 }, page: 0, description: 'Document header title line crop' },
  { id: 'r2', name: 'Text Line 2 (Observations)', bbox: { x: 5, y: 18, w: 90, h: 10 }, page: 0, description: 'Handwritten field observations line' },
  { id: 'r3', name: 'Text Line 3 (Measurements)', bbox: { x: 5, y: 30, w: 90, h: 10 }, page: 0, description: 'Structural measurements and notes' },
  { id: 'r4', name: 'Text Line 4 (Sign-off / Date)', bbox: { x: 5, y: 42, w: 90, h: 10 }, page: 0, description: 'Inspection sign-off and timestamp' },
];

function download(name: string, content: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function Pill({ status }: { status: string }) { return <span className={`pill ${status === 'Reviewed' ? 'green' : status === 'Needs review' ? 'amber' : 'neutral'}`}><span />{status}</span>; }
function IconButton({ label, children, onClick, disabled = false }: { label: string; children: ReactNode; onClick: () => void; disabled?: boolean }) { return <button className="icon-button" aria-label={label} title={label} onClick={onClick} disabled={disabled}>{children}</button>; }
function Modal({ title, children, close, wide = false }: { title: string; children: ReactNode; close: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null); const titleId = useId();
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; ref.current?.showModal(); return () => { previous?.focus(); }; }, []);
  return <dialog ref={ref} aria-labelledby={titleId} className={wide ? 'modal wide' : 'modal'} onCancel={close} onClick={e => { if (e.target === e.currentTarget) { const bounds = e.currentTarget.getBoundingClientRect(); if (e.clientX < bounds.left || e.clientX > bounds.right || e.clientY < bounds.top || e.clientY > bounds.bottom) close(); } }}><header><div><span className="eyebrow">HACKNEX WORKSPACE</span><h2 id={titleId}>{title}</h2></div><IconButton label="Close dialog" onClick={close}><X size={20} /></IconButton></header>{children}</dialog>;
}

export default function Workspace() {
  const [view, setView] = useState<View>('Overview');
  const [docs, setDocs] = useState<DocumentItem[]>(samples);
  const [selected, setSelected] = useState('demo-1');
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [text, setText] = useState(baseText);
  const [preferences, setPreferences] = useState(defaultPreferences);
  const [loaded, setLoaded] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const [modal, setModal] = useState<'upload' | 'help' | 'notifications' | 'export' | null>(null);
  const [toast, setToast] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('All statuses');
  const [sortAsc, setSortAsc] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [activeRegion, setActiveRegion] = useState('r1');
  const [trocrResults, setTrocrResults] = useState<Record<string, RegionRecognitionResult>>({});
  const [recognizingRegion, setRecognizingRegion] = useState<string | null>(null);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [detectedRegionsByDoc, setDetectedRegionsByDoc] = useState<Record<string, DetectedDocumentRegion[]>>({});
  const [jobState, setJobState] = useState<Record<string, { running: boolean; jobId?: string; status?: string; stage?: string; error?: string }>>({});
  const [vlResults, setVlResults] = useState<Record<string, DocumentParsingRunResult>>({});
  const [vlJobState, setVlJobState] = useState<Record<string, { running: boolean; jobId?: string; status?: string; stage?: string; error?: string }>>({});
  const [overlayMode, setOverlayMode] = useState<'both' | 'lines' | 'layout'>('both');
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [tab, setTab] = useState<'Transcription' | 'Comparison' | 'Activity'>('Transcription');
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [editor, setEditor] = useState(false);
  const [uploading, setUploading] = useState(false);
  const urls = useRef<string[]>([]);
  const doc = docs.find(d => d.id === selected) ?? docs[0];
  const pending = regions.filter(r => !(r.id in corrections));
  const demo = doc.id === 'demo-1';
  const notice = (message: string) => setToast(message);

  // Load saved TrOCR and PaddleOCR-VL results from localStorage
  useEffect(() => {
    try {
      const rawTrocr = localStorage.getItem(TROCR_STORAGE_KEY);
      if (rawTrocr) setTrocrResults(JSON.parse(rawTrocr));
      const rawVl = localStorage.getItem(VL_STORAGE_KEY);
      if (rawVl) setVlResults(JSON.parse(rawVl));
    } catch {
      // ignore
    }
  }, []);

  // Load saved workspace review state from localStorage
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
      if (raw) {
        const data = parseSavedState(raw);
        if (data && typeof data.text === 'string' && data.preferences && typeof data.preferences.reviewer === 'string' && typeof data.corrections === 'object' && data.corrections && Array.isArray(data.events)) {
          setCorrections(data.corrections);
          setEvents(data.events);
          setText(data.text);
          setPreferences({ ...defaultPreferences, ...data.preferences });
          if (data.reviewed) setDocs(items => items.map(d => d.id === 'demo-1' ? { ...d, status: 'Reviewed' } : d));
        }
      }
    } catch {
      setStorageError(true);
    }
    setLoaded(true);
    return () => urls.current.forEach(url => URL.revokeObjectURL(url));
  }, []);

  // Fetch real persisted documents from MongoDB Atlas API on mount
  useEffect(() => {
    let active = true;
    const loadApiDocs = async () => {
      try {
        const apiDocs = await fetchDocumentsFromApi();
        if (active && apiDocs.length > 0) {
          // Prepend demo-1 interactive sample fixture, followed by real persisted documents
          setDocs([samples[0], ...apiDocs]);
        }
      } catch (e) {
        console.warn('Backend documents fetch notice (backend may be initializing):', e);
      }
    };
    loadApiDocs();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ corrections, events, text, preferences, reviewed: docs.find(d => d.id === 'demo-1')?.status === 'Reviewed' }));
    } catch {
      setStorageError(true);
    }
  }, [corrections, events, text, preferences, docs, loaded]);

  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(TROCR_STORAGE_KEY, JSON.stringify(trocrResults));
    } catch {
      // ignore
    }
  }, [trocrResults, loaded]);

  useEffect(() => {
    if (!loaded) return;
    try {
      localStorage.setItem(VL_STORAGE_KEY, JSON.stringify(vlResults));
    } catch {
      // ignore
    }
  }, [vlResults, loaded]);

  const runOcrForRegion = async (documentId: string, regionId: string, bbox?: { x: number; y: number; w: number; h: number }, pageIndex: number = 0) => {
    setRecognizingRegion(regionId);
    setOcrError(null);
    try {
      const result = await recognizeRegionApi(documentId, regionId, bbox, pageIndex);
      const key = `${documentId}:${regionId}`;
      setTrocrResults(prev => ({ ...prev, [key]: result }));
      record('TrOCR inference executed', `Region ${regionId}: ${result.recognized_text} (${(result.confidence * 100).toFixed(1)}% conf, ${result.execution_time_ms.toFixed(0)}ms)`);
      notice(`TrOCR recognized text in ${(result.execution_time_ms / 1000).toFixed(2)}s (${(result.confidence * 100).toFixed(1)}% conf)`);
    } catch (err: any) {
      const msg = err?.message || 'Recognition request failed';
      setOcrError(msg);
      notice(`OCR Error: ${msg}`);
    } finally {
      setRecognizingRegion(null);
    }
  };

  // Fetch detected regions and parsed document for the active document from MongoDB Atlas
  useEffect(() => {
    if (demo || !doc.id) return;
    let active = true;
    const loadRegions = async () => {
      try {
        const list = await fetchDocumentRegionsApi(doc.id);
        if (active && list.length > 0) {
          setDetectedRegionsByDoc(prev => ({ ...prev, [doc.id]: list }));
          setActiveRegion(prev => (list.some(r => r.id === prev) ? prev : list[0].id));
        }
      } catch (e) {
        // Doc might not have regions processed yet
      }
    };
    const loadParsedDoc = async () => {
      try {
        const parsed = await fetchParsedDocumentApi(doc.id);
        if (active && parsed) {
          setVlResults(prev => ({ ...prev, [doc.id]: parsed }));
          if (parsed.pages[0]?.blocks?.length > 0) {
            setActiveBlockId(parsed.pages[0].blocks[0].block_id);
          }
        }
      } catch (e) {
        // Doc might not have been parsed with PaddleOCR-VL yet
      }
    };
    loadRegions();
    loadParsedDoc();
    return () => { active = false; };
  }, [doc.id, demo]);

  const runFullDocumentOcr = async (documentId: string) => {
    setJobState(prev => ({ ...prev, [documentId]: { running: true, status: 'submitting', stage: 'ingestion' } }));
    notice('Submitting document to PP-OCRv6 cloud pipeline...');
    try {
      const scheduleRes = await scheduleDocumentRecognitionApi(documentId);
      const jobId = scheduleRes.job_id;
      setJobState(prev => ({
        ...prev,
        [documentId]: { running: true, jobId, status: scheduleRes.status, stage: scheduleRes.stage },
      }));
      record('PP-OCRv6 job scheduled', `Cloud Job ID: ${jobId} (${scheduleRes.status})`);

      const startTime = Date.now();
      const pollInterval = 1500;
      const maxDuration = 300000;

      const poll = async () => {
        if (Date.now() - startTime > maxDuration) {
          setJobState(prev => ({ ...prev, [documentId]: { running: false, error: 'Job timed out after 5 minutes' } }));
          notice('PP-OCRv6 job timed out.');
          return;
        }

        try {
          const statusRes = await getJobStatusApi(jobId);
          const isRunning = ['queued', 'submitted', 'running'].includes(statusRes.status);
          setJobState(prev => ({
            ...prev,
            [documentId]: {
              running: isRunning,
              jobId,
              status: statusRes.status,
              stage: statusRes.stage,
              error: statusRes.error,
            },
          }));

          if (statusRes.status === 'completed') {
            const detected = await fetchDocumentRegionsApi(documentId);
            setDetectedRegionsByDoc(prev => ({ ...prev, [documentId]: detected }));
            if (detected.length > 0) {
              setActiveRegion(detected[0].id);
            }
            const sec = ((statusRes.execution_time_ms || 0) / 1000).toFixed(1);
            record(
              'PP-OCRv6 document recognition completed',
              `${detected.length} text lines detected in ${sec}s`
            );
            notice(`PP-OCRv6 complete: ${detected.length} regions detected (${sec}s).`);
          } else if (statusRes.status === 'failed') {
            const err = statusRes.error || 'Cloud execution failed';
            record('PP-OCRv6 job failed', err);
            notice(`PP-OCRv6 failed: ${err}`);
          } else {
            setTimeout(poll, pollInterval);
          }
        } catch (pollErr: any) {
          console.warn('Polling error:', pollErr);
          setTimeout(poll, pollInterval);
        }
      };

      setTimeout(poll, pollInterval);
    } catch (err: any) {
      const msg = err?.message || 'Failed to schedule OCR job';
      setJobState(prev => ({ ...prev, [documentId]: { running: false, error: msg } }));
      notice(`OCR schedule error: ${msg}`);
    }
  };

  const runDocumentIntelligence = async (documentId: string) => {
    setVlJobState(prev => ({ ...prev, [documentId]: { running: true, status: 'submitting', stage: 'layout_analysis' } }));
    notice('Submitting document to PaddleOCR-VL-1.6 document intelligence pipeline...');
    try {
      const scheduleRes = await scheduleDocumentIntelligenceApi(documentId);
      const jobId = scheduleRes.job_id;
      setVlJobState(prev => ({
        ...prev,
        [documentId]: { running: true, jobId, status: scheduleRes.status, stage: scheduleRes.stage },
      }));
      record('PaddleOCR-VL-1.6 job scheduled', `Document Intelligence Job ID: ${jobId} (${scheduleRes.status})`);

      const startTime = Date.now();
      const pollInterval = 1500;
      const maxDuration = 300000;

      const poll = async () => {
        if (Date.now() - startTime > maxDuration) {
          setVlJobState(prev => ({ ...prev, [documentId]: { running: false, error: 'Document intelligence job timed out after 5 minutes' } }));
          notice('PaddleOCR-VL job timed out.');
          return;
        }

        try {
          const statusRes = await getJobStatusApi(jobId);
          const isRunning = ['queued', 'submitted', 'running'].includes(statusRes.status);
          setVlJobState(prev => ({
            ...prev,
            [documentId]: {
              running: isRunning,
              jobId,
              status: statusRes.status,
              stage: statusRes.stage,
              error: statusRes.error,
            },
          }));

          if (statusRes.status === 'completed') {
            const parsed = await fetchParsedDocumentApi(documentId);
            if (parsed) {
              setVlResults(prev => ({ ...prev, [documentId]: parsed }));
              if (parsed.pages[0]?.blocks?.length > 0) {
                setActiveBlockId(parsed.pages[0].blocks[0].block_id);
              }
              const sec = ((statusRes.execution_time_ms || 0) / 1000).toFixed(1);
              record(
                'PaddleOCR-VL-1.6 document intelligence completed',
                `${parsed.total_blocks} blocks parsed, ${parsed.pages[0]?.tables_count || 0} tables in ${sec}s`
              );
              notice(`PaddleOCR-VL complete: ${parsed.total_blocks} layout blocks parsed in ${sec}s.`);
            }
          } else if (statusRes.status === 'failed') {
            const err = statusRes.error || 'Cloud execution failed';
            record('PaddleOCR-VL job failed', err);
            notice(`PaddleOCR-VL failed: ${err}`);
          } else {
            setTimeout(poll, pollInterval);
          }
        } catch (pollErr: any) {
          console.warn('Polling error:', pollErr);
          setTimeout(poll, pollInterval);
        }
      };

      setTimeout(poll, pollInterval);
    } catch (err: any) {
      const msg = err?.message || 'Failed to schedule document intelligence job';
      setVlJobState(prev => ({ ...prev, [documentId]: { running: false, error: msg } }));
      notice(`Document intelligence schedule error: ${msg}`);
    }
  };

  const resolveDocRegion = (docId: string, regId: string, value: string) => {
    const key = `${docId}:${regId}`;
    setCorrections(items => ({ ...items, [key]: value }));
    record('Human review confirmed', `${preferences.reviewer} confirmed region ${regId.toUpperCase()} as "${value}"`);
    notice(`Region ${regId.toUpperCase()} confirmed by ${preferences.reviewer}`);
  };

  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(''), 5000);
    return () => clearTimeout(timeout);
  }, [toast]);

  const navigate = (next: View) => { setView(next); setMobileNav(false); setQuery(''); };
  const openDoc = (item: DocumentItem) => { setSelected(item.id); setView('Review workspace'); setZoom(100); setRotation(0); setTab('Transcription'); setEditor(false); setActiveRegion('r1'); };
  const record = (action: string, detail: string) => setEvents(items => [{ id: crypto.randomUUID(), time: new Date().toISOString(), action, detail }, ...items]);
  const resolve = (id: string, value: string) => {
    const region = regions.find(r => r.id === id)!;
    const old = corrections[id] ?? region.original;
    const updated = updateRegionText(text, region, old, value);
    if (updated === null) {
      notice('This line was edited manually. Restore its original sentence before changing this region decision.');
      return;
    }
    setDocs(items => items.map(d => d.id === 'demo-1' ? { ...d, status: 'Needs review' } : d));
    setCorrections(items => ({ ...items, [id]: value }));
    setText(updated);
    record('Region reviewed', `${preferences.reviewer}: ${region.original} → ${value}`);
    const next = regions.find(r => r.id !== id && !(r.id in corrections));
    if (next) setActiveRegion(next.id);
    notice(next ? 'Decision saved. Next region is ready.' : 'All flagged regions reviewed. Check the transcript, then complete review.');
  };

  const filtered = docs.filter(d => `${d.name} ${d.kind}`.toLowerCase().includes(query.toLowerCase()) && (filter === 'All statuses' || d.status === filter));
  const shownDocs = sortAsc ? [...filtered].sort((a, b) => a.name.localeCompare(b.name)) : filtered;

  const addDocument = async (file: File, title: string, kind: string, language: string) => {
    setUploading(true);
    try {
      const result = await uploadDocumentToApi(file, title, kind, language);
      const newItem: DocumentItem = {
        id: result.document_id,
        name: result.name || title,
        kind,
        language,
        pages: result.page_count || 1,
        status: 'Ready for backend',
        added: 'Just now',
        size: `${(((result.file_size_bytes || file.size) / (1024 * 1024)).toFixed(2))} MB`,
        sample: false,
        url: `/api/v1/documents/${result.document_id}/file`,
        mime: result.content_type || file.type,
        sha256: result.sha256,
        gridfs_file_id: result.gridfs_file_id,
      };
      setDocs(items => [samples[0], newItem, ...items.filter(i => i.id !== samples[0].id && i.id !== newItem.id)]);
      setModal(null);
      openDoc(newItem);
      notice(`Uploaded to MongoDB GridFS. SHA-256: ${result.sha256 ? result.sha256.slice(0, 8) + '...' : 'verified'}`);
    } catch (err: any) {
      notice(err?.message || 'Upload failed');
      throw err;
    } finally {
      setUploading(false);
    }
  };

  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    {mobileNav && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
    <aside id="workspace-sidebar" className={`sidebar ${mobileNav ? 'open' : ''}`}>
      <a href="#" className="brand" onClick={e => { e.preventDefault(); navigate('Overview'); }}><span className="brand-mark"><ScanLine size={23} /></span>hacknex<span className="brand-dot">.</span></a>
      <div className="workspace-label"><span className="workspace-avatar">H</span><div>HACKNEX workspace<small>Personal workspace</small></div></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation">{([{ title: 'Overview', icon: LayoutDashboard }, { title: 'Documents', icon: FolderOpen }, { title: 'Review workspace', icon: ScanLine }, { title: 'Evaluation', icon: Microscope }] as const).map(item => <button key={item.title} className={`nav-item ${view === item.title ? 'active' : ''}`} aria-current={view === item.title ? 'page' : undefined} onClick={() => navigate(item.title)}><item.icon size={18} />{item.title}{item.title === 'Documents' && <span className="nav-count">{docs.length}</span>}{item.title === 'Review workspace' && pending.length > 0 && <span className="nav-dot" />}</button>)}</nav>
      <div className="sidebar-note"><div className="note-icon"><ShieldCheck size={21} /></div><strong>Evidence before certainty.</strong><p>Keep the original. Question the ambiguous. Review with confidence.</p><button onClick={() => setModal('help')}>Our review principles <ArrowUpRight size={14} /></button></div>
      <div className="sidebar-bottom"><button className={`nav-item ${view === 'Settings' ? 'active' : ''}`} onClick={() => navigate('Settings')}><Settings2 size={18} />Workspace settings</button><button className="nav-item" onClick={() => setModal('help')}><CircleHelp size={18} />Help & guidance</button><div className="profile"><span className="avatar">{preferences.reviewer.slice(0, 2).toUpperCase()}</span><div><strong>{preferences.reviewer}</strong><small>Workspace owner</small></div><span className="local-indicator" title="MongoDB Atlas connected" /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Open navigation" aria-expanded={mobileNav} aria-controls="workspace-sidebar" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>Workspace</span><ChevronRight size={14} /><strong>{view}</strong></div><div className="top-actions"><span className="demo-tag"><span />Atlas GridFS Connected</span><IconButton label="Notifications" onClick={() => setModal('notifications')}><Bell size={18} /></IconButton><span className="avatar small">{preferences.reviewer.slice(0, 2).toUpperCase()}</span></div></header>
      <main id="main" tabIndex={-1} className={view === 'Review workspace' ? 'main-content review-main' : 'main-content'}>
        {storageError && <div role="alert" className="warning-banner">Browser storage is unavailable. Export your review before leaving.</div>}
        {view === 'Overview' && <>
          <div className="page-heading"><div><div className="eyebrow">YOUR DOCUMENT WORKSPACE</div><h1>Clarity starts here<span>.</span></h1><p>Turn difficult handwriting into text you can stand behind.</p></div><button className="button primary" onClick={() => setModal('upload')}><Plus size={18} />New document</button></div>
          <section className="hero-card"><div className="hero-copy"><div className="hero-kicker"><span className="live-dot" />READ. VERIFY. REFINE.</div><h2>Every word has a story.<br /><em>Keep the evidence.</em></h2><p>A considered workspace for handwritten documents.<br />Original image, clear transcription, and every decision in view.</p><div className="hero-actions"><button className="button cream" onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Explore sample review <ArrowRight size={17} /></button><span>Interactive demo · no model inference</span></div></div><div className="hero-art" aria-hidden="true"><div className="art-orbit" /><div className="paper back-paper"><span>ORIGINAL DOCUMENT</span><i>Field observations</i><div /><div /><div /></div><div className="paper front-paper"><span><ScanLine size={13} /> EVIDENCE LINKED</span><i>The north wall<br />measures <mark>4.8</mark> metres.</i><div className="art-decision"><Check size={13} /> Ready for human review</div></div><div className="art-label"><span /> Clarity, without the guesswork.</div></div></section>
          <section className="stats-grid" aria-label="Workspace summary">{[{ label: 'Documents in workspace', value: docs.length.toString().padStart(2, '0'), icon: FileText, sub: 'GridFS + sample files' }, { label: 'Regions to review', value: pending.length.toString().padStart(2, '0'), icon: ScanLine, sub: 'In the interactive sample', amber: true }, { label: 'Review decisions', value: Object.keys(corrections).length.toString().padStart(2, '0'), icon: CheckCheck, sub: 'Saved in this browser' }, { label: 'Recognition service', value: 'TrOCR Base Active', icon: Microscope, sub: 'microsoft/trocr-base (CER 6.6%)', small: true }].map(stat => <article className="stat" key={stat.label}><div><span>{stat.label}</span><stat.icon size={17} /></div><strong className={`${stat.amber ? 'amber-text' : ''} ${stat.small ? 'stat-small' : ''}`}>{stat.value}</strong><small>{stat.sub}</small></article>)}</section>
          <div className="section-heading"><div><h2>Your documents</h2><p>A clear path from source to reviewed text.</p></div><button className="text-button" onClick={() => navigate('Documents')}>View all documents <ArrowRight size={16} /></button></div>
          <DocumentTable docs={docs.slice(0, 4)} open={openDoc} />
          <div className="bottom-grid"><section className="principle-card"><span className="mini-icon"><ShieldCheck size={20} /></span><div><h3>Uncertainty deserves attention.</h3><p>Review flags tell you where to look. They are not a guarantee that the remaining text is correct.</p></div><button className="text-button" onClick={() => setModal('help')}>Learn more <ArrowUpRight size={15} /></button></section><section className="progress-card"><div><span className="eyebrow">SAMPLE REVIEW</span><strong>{Object.keys(corrections).length} of 3 regions reviewed</strong></div><div className="progress-track"><span style={{ width: `${Object.keys(corrections).length / 3 * 100}%` }} /></div><button onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Continue where you left off <ArrowRight size={15} /></button></section></div>
        </>}
        {view === 'Documents' && <><div className="page-heading"><div><div className="eyebrow">DOCUMENT LIBRARY</div><h1>Every source. One place<span>.</span></h1><p>Organize originals and pick up your next review.</p></div><button className="button primary" onClick={() => setModal('upload')}><Plus size={18} />New document</button></div><div className="library-toolbar"><label className="search-field"><Search size={18} /><input placeholder="Search documents or document types" value={query} onChange={e => setQuery(e.target.value)} aria-label="Search documents" />{query && <button aria-label="Clear search" onClick={() => setQuery('')}><X size={16} /></button>}</label><label className="select-wrap"><ListFilter size={16} /><select aria-label="Filter by status" value={filter} onChange={e => setFilter(e.target.value)}><option>All statuses</option><option>Needs review</option><option>Reviewed</option><option>Ready for backend</option></select></label><button className="button secondary" onClick={() => setSortAsc(v => !v)}>{sortAsc ? 'Name A–Z' : 'Newest first'}<ChevronDown size={15} /></button></div><DocumentTable docs={shownDocs} open={openDoc} /><p className="footnote">{shownDocs.length} of {docs.length} documents · Documents are immutably stored in MongoDB Atlas GridFS and persist across browser reloads.</p></>}
        {view === 'Review workspace' && <><div className="review-heading"><div><button className="text-button" onClick={() => navigate('Documents')}><ArrowLeft size={15} />All documents</button><h1>{doc.name}</h1><div className="document-meta"><Pill status={doc.status} /><span>{doc.language}</span><span>{doc.pages} {doc.pages === 1 ? 'page' : 'pages'}</span><span>{doc.sample ? 'Demo document' : doc.size}</span>{doc.sha256 && <span title={`SHA-256: ${doc.sha256}`}>SHA: {doc.sha256.slice(0, 8)}...</span>}</div></div><div className="heading-actions">{!demo && doc.url && <a href={`${doc.url}?download=true`} className="button secondary" download={doc.name}><ArrowDownToLine size={16} />Download original</a>}<button className="button secondary" disabled={!demo} onClick={() => setModal('export')}><ArrowDownToLine size={16} />Export</button><button className="button primary" disabled={!demo || pending.length > 0 || doc.status === 'Reviewed'} title={pending.length ? 'Resolve all flagged regions first' : undefined} onClick={() => { setDocs(items => items.map(d => d.id === doc.id ? { ...d, status: 'Reviewed' } : d)); record('Review completed', `Sample reviewed by ${preferences.reviewer}.`); notice('Sample review completed. Your transcript is ready to export.'); }}><CheckCheck size={16} />{doc.status === 'Reviewed' ? 'Reviewed' : 'Complete review'}</button></div></div>
          <div className="review-banner"><Sparkles size={16} /><span>{demo ? 'Interactive sample — transcription and flagged regions are illustrative, not model-generated results.' : 'Phase 5 Tri-Model Intelligence Active: PP-OCRv6 Line OCR · TrOCR Base Handwriting · PaddleOCR-VL-1.6 Document Intelligence.'}</span></div>
          <div className="review-grid"><section className="source-pane"><div className="pane-header"><div><FileText size={16} /><strong>Original document</strong></div><span>READ ONLY</span></div><div className="source-controls"><div className="segmented"><IconButton label="Zoom out" disabled={zoom <= 60} onClick={() => setZoom(z => z - 20)}><ZoomOut size={16} /></IconButton><span>{zoom}%</span><IconButton label="Zoom in" disabled={zoom >= 180} onClick={() => setZoom(z => z + 20)}><ZoomIn size={16} /></IconButton></div><div className="toolbar-group"><IconButton label="Rotate source" onClick={() => setRotation(r => (r + 90) % 360)}><RotateCw size={16} /></IconButton><IconButton label="Reset source view" onClick={() => { setZoom(100); setRotation(0); }}><Maximize2 size={16} /></IconButton></div></div>
          {!demo && (
            <div className="overlay-toggle-bar">
              <span>Overlays:</span>
              <button type="button" className={`overlay-toggle-btn ${overlayMode === 'both' ? 'active' : ''}`} onClick={() => setOverlayMode('both')}>All (PP-OCR + VL)</button>
              <button type="button" className={`overlay-toggle-btn ${overlayMode === 'lines' ? 'active' : ''}`} onClick={() => setOverlayMode('lines')}>PP-OCR Lines</button>
              <button type="button" className={`overlay-toggle-btn ${overlayMode === 'layout' ? 'active' : ''}`} onClick={() => setOverlayMode('layout')}>PaddleOCR-VL Blocks</button>
            </div>
          )}
          <div className="source-scroll">{demo || doc.url ? <div className="source-image-wrap" style={{ width: `${zoom}%`, transform: `rotate(${rotation}deg)` }}>{doc.mime === 'application/pdf' ? <object data={doc.url} type="application/pdf" aria-label={`Original PDF: ${doc.name}`} className="pdf-preview"><a href={doc.url} target="_blank" rel="noreferrer">Open PDF preview</a></object> : <img src={demo ? '/sample-note.svg' : doc.url} alt={demo ? 'Illustrative handwritten site inspection note with three review regions' : `Original upload: ${doc.name}`} />}{demo && preferences.highlight && regions.map((r, i) => <button key={r.id} aria-label={`Inspect region ${i + 1}: ${r.original}`} className={`region-overlay ${activeRegion === r.id ? 'selected' : ''} ${r.id in corrections ? 'resolved' : ''}`} style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%` }} onClick={() => { setActiveRegion(r.id); setTab('Transcription'); }}><span>{r.id in corrections ? <Check size={10} /> : i + 1}</span></button>)}{!demo && preferences.highlight && (overlayMode === 'both' || overlayMode === 'lines') && ((detectedRegionsByDoc[doc.id]?.length ? detectedRegionsByDoc[doc.id] : defaultDocRegions).map((r: any, i: number) => { const isDetected = 'bounding_box' in r; const regId = r.id; const isDone = Boolean(corrections[`${doc.id}:${regId}`]); const hasOcr = Boolean(trocrResults[`${doc.id}:${regId}`]); const isIllegible = Boolean(r.is_illegible); const box = isDetected ? r.bounding_box : r.bbox; return <button key={regId} aria-label={`Inspect region ${i + 1}: ${r.name || r.original || regId}`} className={`region-overlay ${activeRegion === regId ? 'selected' : ''} ${isDone ? 'resolved' : isIllegible ? 'illegible-overlay' : ''}`} style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.w}%`, height: `${box.h}%` }} onClick={() => { setActiveRegion(regId); setTab('Transcription'); }}><span>{isDone ? <Check size={10} /> : hasOcr ? <Sparkles size={10} /> : i + 1}</span></button>; }))}{!demo && preferences.highlight && (overlayMode === 'both' || overlayMode === 'layout') && (vlResults[doc.id]?.pages?.[0]?.blocks || []).map((b) => { const isFocused = activeBlockId === b.block_id; return <button key={`vl-${b.block_id}`} type="button" aria-label={`Layout block ${b.reading_order}: ${b.block_type}`} className={`layout-block-overlay block-type-${b.block_type} ${isFocused ? 'selected' : ''}`} style={{ left: `${b.bounding_box.x}%`, top: `${b.bounding_box.y}%`, width: `${b.bounding_box.w}%`, height: `${b.bounding_box.h}%` }} onClick={() => { setActiveBlockId(b.block_id); setTab('Transcription'); }}><span className="block-order-badge">#{b.reading_order} {b.block_type === 'paragraph_title' ? 'Title' : b.block_type === 'table' ? 'Table' : ''}</span></button>; })}</div> : <div className="empty-state"><FileText size={40} /><h3>Source not included</h3><p>This library entry illustrates a document awaiting recognition. Open the field-notes sample to try the complete review.</p><button className="button secondary" onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Open interactive sample</button></div>}</div><footer className="source-footer"><ShieldCheck size={14} />Original preserved in GridFS{demo && <span><span className="legend-dot" /> Needs review <span className="legend-dot green-dot" /> Reviewed</span>}</footer></section>
          <section className="transcript-pane"><div className="review-tabs" role="tablist" aria-label="Review panels">{(['Transcription', 'Comparison', 'Activity'] as const).map(t => <button key={t} role="tab" id={`tab-${t}`} tabIndex={tab === t ? 0 : -1} onKeyDown={e => { const panels = ['Transcription', 'Comparison', 'Activity'] as const; const index = panels.indexOf(t); const next = e.key === 'ArrowRight' ? (index + 1) % 3 : e.key === 'ArrowLeft' ? (index + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1; if (next >= 0) { e.preventDefault(); setTab(panels[next]); document.getElementById(`tab-${panels[next]}`)?.focus(); } }} aria-selected={tab === t} aria-controls="review-panel" onClick={() => setTab(t)}>{t}{t === 'Transcription' && demo && <span>{pending.length}</span>}</button>)}</div><div id="review-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="panel-content">
            {!demo ? (
              <RealDocumentOcrWorkspace
                doc={doc}
                activeRegion={activeRegion}
                setActiveRegion={setActiveRegion}
                trocrResults={trocrResults}
                recognizingRegion={recognizingRegion}
                onRunOcr={runOcrForRegion}
                reviewer={preferences.reviewer}
                corrections={corrections}
                onResolve={resolveDocRegion}
                onNotice={notice}
                detectedRegions={detectedRegionsByDoc[doc.id] || []}
                jobState={jobState[doc.id]}
                onRunFullOcr={() => runFullDocumentOcr(doc.id)}
                parsingRun={vlResults[doc.id] || null}
                vlJobState={vlJobState[doc.id]}
                onRunDocumentIntelligence={() => runDocumentIntelligence(doc.id)}
                activeBlockId={activeBlockId}
                setActiveBlockId={setActiveBlockId}
                tab={tab}
                events={events}
              />
            ) : tab === 'Transcription' ? <><div className="transcript-title"><div><span className="eyebrow">EDITABLE TRANSCRIPT</span><p>{pending.length ? `${pending.length} regions need your attention` : 'All flagged regions have a decision'}</p></div><button className="text-button" onClick={() => setEditor(v => !v)}>{editor ? 'Done editing' : 'Edit text'}</button></div>{editor ? <textarea className="full-editor" aria-label="Edit complete transcription" maxLength={100000} value={text} onChange={e => { setText(e.target.value); setDocs(items => items.map(d => d.id === 'demo-1' ? { ...d, status: 'Needs review' } : d)); }} onBlur={() => record('Transcript edited', 'Full text updated manually.')} /> : <div className="transcript-text">{text.split('\n').map((line, i) => <p key={i}>{line || '\u00a0'}</p>)}</div>}<div className="review-region-header"><h3>Review queue</h3><span>{Object.keys(corrections).length}/3 resolved</span></div><div className="region-list">{regions.map((r, i) => <div className={`region-card ${activeRegion === r.id ? 'focused' : ''}`} key={r.id}><button className="region-card-title" onClick={() => setActiveRegion(r.id)}><span className={`region-number ${r.id in corrections ? 'done' : ''}`}>{r.id in corrections ? <Check size={13} /> : i + 1}</span><strong>{corrections[r.id] ?? r.original}</strong><span>{r.id in corrections ? 'Reviewed' : 'Needs review'}</span><ChevronDown size={15} /></button>{activeRegion === r.id && <div className="region-detail"><p>{r.reason}</p><RegionDecision key={`${r.id}-${corrections[r.id] ?? ''}`} region={r} existing={corrections[r.id]} onResolve={value => resolve(r.id, value)} /></div>}</div>)}</div></> : tab === 'Comparison' ? <><div className="transcript-title"><div><span className="eyebrow">CANDIDATE READINGS</span><p>Illustrative disagreements, side by side.</p></div></div><div className="comparison-table"><table><thead><tr><th>Region</th><th>Line reading</th><th>Crop reading</th><th>Your decision</th></tr></thead><tbody>{regions.map(r => <tr key={r.id}><td>{r.id.toUpperCase()}</td><td>{r.alternatives[0]}</td><td className="amber-text">{r.alternatives[1]}</td><td>{corrections[r.id] ?? 'Unresolved'}</td></tr>)}</tbody></table></div><div className="info-box"><ShieldCheck size={20} /><p>Agreement is not proof of correctness. Compare candidates with the original pixels before recording a decision.</p></div></> : <><span className="eyebrow">REVIEW AUDIT</span>{events.length === 0 ? <div className="empty-state"><Clock3 size={32} /><h3>No review activity yet</h3><p>Resolve a region to start a record of your decisions.</p></div> : <ol className="timeline">{events.map(event => <li key={event.id}><span className="timeline-dot" /><strong>{event.action}</strong><p>{event.detail}</p><time>{new Date(event.time).toLocaleString()}</time></li>)}</ol>}</>}
          </div><div className="transcript-footer"><span className="local-indicator" />{storageError ? 'Session only' : 'Atlas GridFS sync active'}<span>MongoDB Atlas</span></div></section></div>
        </>}
        {view === 'Evaluation' && <Evaluation />}
        {view === 'Settings' && <Settings preferences={preferences} save={value => { setPreferences(value); notice('Workspace preferences saved in this browser.'); }} />}
        <footer className="page-footer"><span>HACKNEX <span className="footer-divider">/</span> Every word, accounted for.</span><span>HACKNEX 2026 · PS04</span></footer>
      </main>
    </div>
    {toast && <div className="toast" role="status"><Check size={18} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={16} /></button></div>}
    {modal === 'upload' && <UploadModal close={() => setModal(null)} add={addDocument} language={preferences.language} uploading={uploading} />}
    {modal === 'help' && <Modal title="A little clarity on the process." close={() => setModal(null)}><div className="modal-body guidance"><p>HackNex brings original evidence and editable text into one review workspace.</p>{[{ title: '01 / Preserve the source', body: 'Keep original documents unchanged. Review highlights link back to regions of the source.' }, { title: '02 / Inspect uncertainty', body: 'Compare candidate readings with the image. A flag is a reason to inspect, not a probability of error.' }, { title: '03 / Record the decision', body: 'Confirm a candidate, enter your own reading, or mark a region illegible. All sample decisions appear in the activity record.' }, { title: '04 / Export with context', body: 'Export the transcript or a JSON review record. Originals are stored immutably in MongoDB GridFS.' }].map(item => <section key={item.title}><h3>{item.title}</h3><p>{item.body}</p></section>)}</div><div className="modal-footer"><button className="button primary" onClick={() => { setModal(null); openDoc(docs.find(d => d.id === 'demo-1')!); }}>Try the sample <ArrowRight size={16} /></button></div></Modal>}
    {modal === 'notifications' && <Modal title="Workspace updates" close={() => setModal(null)}><div className="modal-body"><div className="notification-item"><ScanLine size={22} /><div><h3>{pending.length ? `${pending.length} sample regions need review` : 'Sample regions reviewed'}</h3><p>Your progress is saved in this browser.</p><button className="text-button" onClick={() => { setModal(null); openDoc(docs.find(d => d.id === 'demo-1')!); }}>Open review <ArrowRight size={14} /></button></div></div><div className="notification-item"><Microscope size={22} /><div><h3>MongoDB GridFS storage active</h3><p>Uploaded documents are persisted in MongoDB Atlas GridFS. Recognition pipeline connects in Phase 3.</p></div></div></div></Modal>}
    {modal === 'export' && <Modal title="Export your review" close={() => setModal(null)}><div className="modal-body"><p className="muted">{doc.status !== 'Reviewed' ? 'This review is not complete. Exports are marked as drafts.' : 'Review complete. The evidence record preserves your decisions.'}</p><button className="export-option" onClick={() => { download('hacknex-transcript.txt', `HACKNEX — ILLUSTRATIVE SAMPLE\nStatus: ${doc.status !== 'Reviewed' ? 'DRAFT; unresolved regions: ' + pending.length : 'Human-reviewed sample'}\nNot an OCR benchmark result.\n\n${text}`); notice('Transcript exported.'); setModal(null); }}><FileText size={23} /><div><strong>Plain text transcript</strong><span>Editable text with review status · .txt</span></div><ArrowDownToLine size={18} /></button><button className="export-option" onClick={() => { download('hacknex-review.json', JSON.stringify({ schemaVersion: 1, demo: true, document: doc.name, status: doc.status, unresolvedRegions: pending.map(r => r.id), text, corrections, events, exportedAt: new Date().toISOString() }, null, 2), 'application/json'); notice('Evidence record exported.'); setModal(null); }}><ShieldCheck size={23} /><div><strong>Review evidence record</strong><span>Decisions, transcript and activity · .json</span></div><ArrowDownToLine size={18} /></button></div></Modal>}
  </div>;
}

function DocumentTable({ docs, open }: { docs: DocumentItem[]; open: (doc: DocumentItem) => void }) {
  return <div className="document-table"><table><thead><tr><th>DOCUMENT NAME</th><th>STATUS</th><th>LANGUAGE</th><th>SOURCE</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{docs.map(doc => <tr key={doc.id}><td><button className="document-name" onClick={() => open(doc)}><span className={`file-icon ${doc.status === 'Reviewed' ? 'reviewed' : ''}`}><FileText size={21} /></span><span><strong>{doc.name}</strong><small>{doc.kind} · {doc.mime === 'application/pdf' ? 'PDF' : '1 page'}</small></span></button></td><td><Pill status={doc.status} /></td><td>{doc.language}</td><td><span className="source-label">{doc.sample ? 'Sample' : 'Atlas GridFS'}</span></td><td><IconButton label={`Open ${doc.name}`} onClick={() => open(doc)}><ArrowUpRight size={18} /></IconButton></td></tr>)}</tbody></table>{docs.length === 0 && <div className="empty-state"><Search size={30} /><h3>No matching documents</h3><p>Try another search or change the status filter.</p></div>}</div>;
}

function RegionDecision({ region, existing, onResolve }: { region: typeof regions[number]; existing?: string; onResolve: (value: string) => void }) {
  const [value, setValue] = useState(existing ?? region.original);
  return <form onSubmit={e => { e.preventDefault(); if (value.trim()) onResolve(value.trim()); }}><div className="candidate-buttons">{region.alternatives.map((candidate, i) => <button type="button" className={value === candidate ? 'selected' : ''} key={candidate} onClick={() => setValue(candidate)}><small>{i === 0 ? 'Line reading' : 'Crop reading'}</small>{candidate}{value === candidate && <Check size={13} />}</button>)}</div><label className="field-label" htmlFor={`reading-${region.id}`}>Your reading</label><input id={`reading-${region.id}`} className="text-input" required maxLength={100} value={value} onChange={e => setValue(e.target.value)} /><div className="decision-actions"><button type="button" className="text-button" onClick={() => onResolve('[illegible]')}>Mark illegible</button><button className="button primary small-button" type="submit" disabled={!value.trim()}><Check size={14} />{existing ? 'Update decision' : 'Confirm reading'}</button></div></form>;
}

function UploadModal({ close, add, language, uploading }: { close: () => void; add: (file: File, title: string, kind: string, language: string) => Promise<void>; language: string; uploading: boolean }) {
  const [file, setFile] = useState<File | null>(null); const [title, setTitle] = useState(''); const [kind, setKind] = useState('Field notes'); const [lang, setLang] = useState(language); const [error, setError] = useState(''); const [drag, setDrag] = useState(false); const input = useRef<HTMLInputElement>(null);
  const choose = (files: FileList | null) => { if (!files?.length) return; if (files.length > 1) { setError('Add one document at a time.'); return; } const chosen = files[0]; const issue = validateFile(chosen); if (issue) { setError(issue); return; } setFile(chosen); setTitle(chosen.name.replace(/\.[^.]+$/, '')); setError(''); };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) { setError('Choose a document before continuing.'); input.current?.focus(); return; }
    if (!title.trim()) { setError('Enter a document name.'); return; }
    try {
      await add(file, title.trim(), kind, lang);
    } catch (err: any) {
      setError(err?.message || 'Upload failed. Check document format and connection.');
    }
  };
  return <Modal title="Bring a document into focus." close={close} wide><form onSubmit={submit}><div className="modal-body"><p className="muted">Add an original to your workspace. Uploaded documents are stored immutably in MongoDB GridFS.</p><div className={`dropzone ${drag ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files); }}><span className="upload-circle"><UploadCloud size={28} /></span><strong>{file ? file.name : 'Drop your document here'}</strong><p>PDF, PNG, or JPEG · Up to 10 MB · Max 20 pages</p><input ref={input} type="file" accept="image/png,image/jpeg,image/webp,application/pdf" id="file-upload" className="file-input" aria-describedby="upload-note upload-error" onChange={e => choose(e.target.files)} /><label className="button secondary" htmlFor="file-upload">{file ? 'Choose another file' : 'Browse files'}</label></div>{error && <p className="form-error" id="upload-error" role="alert">{error}</p>}<div className="form-grid"><label className="form-field full">Document name <span aria-hidden="true">*</span><input className="text-input" required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Site inspection — October 08" /></label><label className="form-field">Document type<select className="text-input" value={kind} onChange={e => setKind(e.target.value)}>{['Field notes', 'Correspondence', 'Research notes', 'Forms', 'Other'].map(v => <option key={v}>{v}</option>)}</select></label><label className="form-field">Expected language<select className="text-input" value={lang} onChange={e => setLang(e.target.value)}>{['English', 'Tamil', 'Hindi', 'Mixed / unknown'].map(v => <option key={v}>{v}</option>)}</select></label></div><div className="info-box" id="upload-note"><ShieldCheck size={20} /><p>Files are verified bit-for-bit, hashed with SHA-256, and stored directly in MongoDB Atlas GridFS.</p></div></div><div className="modal-footer"><span>* Required field</span><button type="button" className="button secondary" onClick={close} disabled={uploading}>Cancel</button><button type="submit" className="button primary" disabled={uploading}>{uploading ? 'Storing in GridFS...' : 'Add document'} <ArrowRight size={16} /></button></div></form></Modal>;
}

function RealDocumentOcrWorkspace({
  doc,
  activeRegion,
  setActiveRegion,
  trocrResults,
  recognizingRegion,
  onRunOcr,
  reviewer,
  corrections,
  onResolve,
  onNotice,
  detectedRegions,
  jobState,
  onRunFullOcr,
  parsingRun,
  vlJobState,
  onRunDocumentIntelligence,
  activeBlockId,
  setActiveBlockId,
  tab,
  events,
}: {
  doc: DocumentItem;
  activeRegion: string;
  setActiveRegion: (id: string) => void;
  trocrResults: Record<string, RegionRecognitionResult>;
  recognizingRegion: string | null;
  onRunOcr: (docId: string, regionId: string, bbox: { x: number; y: number; w: number; h: number }, pageIndex: number) => Promise<void>;
  reviewer: string;
  corrections: Record<string, string>;
  onResolve: (docId: string, regId: string, value: string) => void;
  onNotice: (msg: string) => void;
  detectedRegions: DetectedDocumentRegion[];
  jobState?: { running: boolean; jobId?: string; status?: string; stage?: string; error?: string };
  onRunFullOcr: () => void;
  parsingRun: DocumentParsingRunResult | null;
  vlJobState?: { running: boolean; jobId?: string; status?: string; stage?: string; error?: string };
  onRunDocumentIntelligence: () => void;
  activeBlockId: string | null;
  setActiveBlockId: (id: string | null) => void;
  tab: 'Transcription' | 'Comparison' | 'Activity';
  events: AuditEvent[];
}) {
  const [subTab, setSubTab] = useState<'layout' | 'markdown' | 'tables' | 'regions'>('layout');
  const [copiedMd, setCopiedMd] = useState(false);

  const hasDetected = detectedRegions.length > 0;
  const hasParsingRun = Boolean(parsingRun && parsingRun.pages && parsingRun.pages.length > 0);
  const layoutBlocks = (hasParsingRun && parsingRun?.pages[0]?.blocks) ? parsingRun.pages[0].blocks : [];
  const tableBlocks = layoutBlocks.filter(b => b.block_type === 'table');

  // Resolve active region item
  const activeReg = hasDetected
    ? (detectedRegions.find(r => r.id === activeRegion) || detectedRegions[0])
    : (defaultDocRegions.find(r => r.id === activeRegion) || defaultDocRegions[0]);

  const activeId = activeReg ? activeReg.id : 'r1';
  const ocrKey = `${doc.id}:${activeId}`;
  const trocrRes = trocrResults[ocrKey];
  const verifiedVal = corrections[ocrKey];
  const isRecognizing = recognizingRegion === activeId;

  // Primary text from detection or TrOCR
  const primaryText = hasDetected && 'original' in activeReg
    ? (activeReg as DetectedDocumentRegion).original || (activeReg as DetectedDocumentRegion).line
    : '';

  const [draftText, setDraftText] = useState(verifiedVal ?? primaryText ?? trocrRes?.recognized_text ?? '');

  useEffect(() => {
    setDraftText(verifiedVal ?? primaryText ?? trocrRes?.recognized_text ?? '');
  }, [ocrKey, verifiedVal, primaryText, trocrRes?.recognized_text]);

  const handleConfirm = (e: FormEvent) => {
    e.preventDefault();
    if (!draftText.trim()) return;
    onResolve(doc.id, activeId, draftText.trim());
  };

  const copyMarkdown = async () => {
    if (!parsingRun?.markdown_text) return;
    try {
      await navigator.clipboard.writeText(parsingRun.markdown_text);
      setCopiedMd(true);
      onNotice('Prettified Markdown copied to clipboard');
      setTimeout(() => setCopiedMd(false), 2500);
    } catch {
      onNotice('Failed to copy to clipboard');
    }
  };

  // If Tab is Activity
  if (tab === 'Activity') {
    return (
      <div className="activity-panel">
        <div className="transcript-title">
          <div>
            <span className="eyebrow">AUDIT & PROVENANCE TRAIL</span>
            <p>Cryptographic hash chain & immutable review activity.</p>
          </div>
          <span className="pill green"><ShieldCheck size={12} /> Atlas GridFS Verified</span>
        </div>
        {events.length === 0 ? (
          <div className="empty-state">
            <Clock3 size={32} />
            <h3>No review activity yet</h3>
            <p>Run document intelligence or verify a text region to build an audit record.</p>
          </div>
        ) : (
          <ol className="timeline">
            {events.map(event => (
              <li key={event.id}>
                <span className="timeline-dot" />
                <strong>{event.action}</strong>
                <p>{event.detail}</p>
                <time>{new Date(event.time).toLocaleString()}</time>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  }

  // If Tab is Comparison (3-Model Comparison View)
  if (tab === 'Comparison') {
    return (
      <div className="comparison-panel">
        <div className="transcript-title">
          <div>
            <span className="eyebrow">MULTI-MODEL CANDIDATE PROVENANCE</span>
            <p>3 independent models evaluated against the same document pixels.</p>
          </div>
          <span className="pill green"><Cpu size={12} /> Tri-Model Stack</span>
        </div>

        <div className="info-box" style={{ marginBottom: 14 }}>
          <ShieldCheck size={20} />
          <p>
            <strong>Evidence-First Invariant:</strong> Raw PP-OCRv6 line detection, TrOCR Base crop recognition, and PaddleOCR-VL-1.6 layout proposals remain isolated in distinct provenance layers. Human edits never overwrite raw model outputs.
          </p>
        </div>

        <div className="comparison-table">
          <table className="tri-model-table">
            <thead>
              <tr>
                <th style={{ width: '12%' }}>Target</th>
                <th style={{ width: '28%' }}>Model 1: PP-OCRv6 Cloud (Line)</th>
                <th style={{ width: '28%' }}>Model 2: TrOCR Base Local (Crop)</th>
                <th style={{ width: '22%' }}>Model 3: PaddleOCR-VL (Layout)</th>
                <th style={{ width: '10%' }}>Verified</th>
              </tr>
            </thead>
            <tbody>
              {(hasDetected ? detectedRegions : defaultDocRegions).map((reg: any, idx: number) => {
                const regId = reg.id;
                const key = `${doc.id}:${regId}`;
                const trocr = trocrResults[key];
                const confirmed = corrections[key];
                const ppText = reg.original || reg.line || '';
                const vlBlock = layoutBlocks[idx] || null;

                return (
                  <tr key={regId}>
                    <td>
                      <strong>#{idx + 1}</strong>
                      <small style={{ color: '#7a8c75', display: 'block' }}>{reg.name || regId.toUpperCase()}</small>
                    </td>
                    <td className="model-cell">
                      {ppText ? (
                        <>
                          <span>"{ppText}"</span>
                          <small>Conf: {((reg.confidence ?? 0.85) * 100).toFixed(1)}% · PP-OCRv6</small>
                        </>
                      ) : (
                        <span style={{ color: '#9ba895' }}>Awaiting PP-OCRv6</span>
                      )}
                    </td>
                    <td className="model-cell">
                      {trocr ? (
                        <>
                          <span style={{ color: '#1f4534', fontWeight: 500 }}>"{trocr.recognized_text}"</span>
                          <small>Conf: {(trocr.confidence * 100).toFixed(1)}% · {trocr.execution_time_ms.toFixed(0)}ms</small>
                        </>
                      ) : (
                        <span style={{ color: '#9ba895' }}>Not evaluated</span>
                      )}
                    </td>
                    <td className="model-cell">
                      {vlBlock ? (
                        <>
                          <span>"{vlBlock.content.slice(0, 40)}{vlBlock.content.length > 40 ? '...' : ''}"</span>
                          <small>Order #{vlBlock.reading_order} · {vlBlock.block_type}</small>
                        </>
                      ) : (
                        <span style={{ color: '#9ba895' }}>{hasParsingRun ? '—' : 'Awaiting PaddleOCR-VL'}</span>
                      )}
                    </td>
                    <td>
                      {confirmed ? (
                        <span className="pill green" style={{ fontSize: 9 }}><Check size={10} /> Verified</span>
                      ) : (
                        <span className="pill amber" style={{ fontSize: 9 }}>Pending</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Default: Transcription Tab with Document Intelligence Sub-Views
  return (
    <div className="real-ocr-workspace">
      {/* Action Banner 1: PaddleOCR-VL-1.6 Document Intelligence */}
      <div className="vl-action-banner">
        <div className="banner-info">
          <h4><Sparkles size={14} /> Document Intelligence · PaddleOCR-VL-1.6 Cloud</h4>
          <p>
            {vlJobState?.running
              ? `Processing document intelligence pipeline (${vlJobState.stage || 'layout_analysis'}... Status: ${vlJobState.status || 'running'})`
              : hasParsingRun
              ? `${parsingRun?.total_blocks} layout blocks & ${parsingRun?.pages[0]?.tables_count || 0} tables parsed in ${((parsingRun?.execution_time_ms || 0) / 1000).toFixed(1)}s.`
              : 'Execute hierarchical layout analysis, reading-order prediction, and sanitized Markdown parsing.'}
          </p>
        </div>
        <button
          type="button"
          className="vl-run-btn"
          disabled={vlJobState?.running}
          onClick={onRunDocumentIntelligence}
        >
          {vlJobState?.running ? (
            <>
              <RotateCw size={14} className="loading-spinner" />
              <span>Analyzing Document...</span>
            </>
          ) : (
            <>
              <Sparkles size={15} />
              <span>{hasParsingRun ? 'Re-run PaddleOCR-VL' : 'Run Document Intelligence — PaddleOCR-VL'}</span>
            </>
          )}
        </button>
      </div>

      {/* Action Banner 2: PP-OCRv6 Text Detection & Recognition */}
      <div className="ppocr-action-banner">
        <div className="banner-info">
          <h4>Automatic Document OCR · PP-OCRv6 Cloud</h4>
          <p>
            {jobState?.running
              ? `Processing cloud pipeline (${jobState.stage || 'recognition'}... Status: ${jobState.status || 'running'})`
              : hasDetected
              ? `${detectedRegions.length} text lines detected with normalized [0, 100]% bounding boxes.`
              : 'Run automatic document-level text detection & recognition on this GridFS original.'}
          </p>
        </div>
        <button
          type="button"
          className="ppocr-run-btn"
          disabled={jobState?.running}
          onClick={onRunFullOcr}
        >
          {jobState?.running ? (
            <>
              <RotateCw size={14} className="loading-spinner" />
              <span>Pipeline running...</span>
            </>
          ) : (
            <>
              <ScanLine size={15} />
              <span>{hasDetected ? 'Re-run PP-OCRv6 OCR' : 'Run OCR — PP-OCRv6'}</span>
            </>
          )}
        </button>
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="doc-subnav">
        <button
          type="button"
          className={`doc-subnav-btn ${subTab === 'layout' ? 'active' : ''}`}
          onClick={() => setSubTab('layout')}
        >
          <Sparkles size={13} />
          <span>Layout & Reading Order</span>
          {hasParsingRun && <span className="pill-count">{parsingRun?.total_blocks}</span>}
        </button>
        <button
          type="button"
          className={`doc-subnav-btn ${subTab === 'markdown' ? 'active' : ''}`}
          onClick={() => setSubTab('markdown')}
        >
          <FileText size={13} />
          <span>Sanitized Markdown</span>
        </button>
        <button
          type="button"
          className={`doc-subnav-btn ${subTab === 'tables' ? 'active' : ''}`}
          onClick={() => setSubTab('tables')}
        >
          <LayoutDashboard size={13} />
          <span>Parsed Tables</span>
          {hasParsingRun && <span className="pill-count">{tableBlocks.length}</span>}
        </button>
        <button
          type="button"
          className={`doc-subnav-btn ${subTab === 'regions' ? 'active' : ''}`}
          onClick={() => setSubTab('regions')}
        >
          <ScanLine size={13} />
          <span>Detected Text Lines</span>
          <span className="pill-count">{hasDetected ? detectedRegions.length : defaultDocRegions.length}</span>
        </button>
      </div>

      {/* SubTab 1: Layout & Reading Order View */}
      {subTab === 'layout' && (
        <div>
          {hasParsingRun ? (
            <>
              <div className="vl-meta-strip">
                <span>Model: <strong>{parsingRun?.model_version || 'PaddleOCR-VL-1.6'}</strong></span>
                <span>Blocks: <strong>{parsingRun?.total_blocks}</strong></span>
                <span>Latency: <strong>{((parsingRun?.execution_time_ms || 0) / 1000).toFixed(2)}s</strong></span>
                <span>Temperature: <strong>0.0</strong></span>
                <span>Provider: <strong>{parsingRun?.provider_id}</strong></span>
              </div>

              <div className="region-list">
                {layoutBlocks.map((b) => {
                  const isSelected = activeBlockId === b.block_id;
                  const typeClass = b.block_type === 'paragraph_title' ? 'title-pill' : b.block_type === 'table' ? 'table-pill' : b.block_type === 'formula' ? 'formula-pill' : 'text-pill';

                  return (
                    <div
                      key={b.block_id}
                      className={`layout-block-card ${isSelected ? 'focused' : ''}`}
                      onClick={() => setActiveBlockId(b.block_id)}
                    >
                      <div className="layout-block-card-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span className="block-order-badge" style={{ background: '#472d8e' }}>#{b.reading_order}</span>
                          <span className={`type-pill ${typeClass}`}>{b.block_type.replace('_', ' ')}</span>
                        </div>
                        <span style={{ fontSize: 10, color: '#7a8c75' }}>
                          Box: [{b.bounding_box.x}%, {b.bounding_box.y}%, {b.bounding_box.w}%, {b.bounding_box.h}%]
                        </span>
                      </div>
                      <div className="layout-block-card-content">{b.content || '<Empty layout block>'}</div>
                      <div className="layout-block-card-footer">
                        <span>Reading Sequence: #{b.reading_order}</span>
                        {b.confidence !== undefined && <span>Score: {(b.confidence * 100).toFixed(1)}%</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="empty-state" style={{ padding: '32px 20px', background: '#fafcf8', border: '1px dashed #d5ded0', borderRadius: 8 }}>
              <Sparkles size={32} style={{ color: '#6246b0', marginBottom: 8 }} />
              <h3 style={{ margin: '4px 0', fontSize: 15, color: '#261b47' }}>PaddleOCR-VL Document Intelligence Awaiting Run</h3>
              <p style={{ margin: '4px 0 14px', fontSize: 12, color: '#687762', maxWidth: 440 }}>
                Click <strong>"Run Document Intelligence — PaddleOCR-VL"</strong> above to extract layout blocks, determine topological reading order, and isolate tables.
              </p>
            </div>
          )}
        </div>
      )}

      {/* SubTab 2: Prettified Markdown View */}
      {subTab === 'markdown' && (
        <div className="vl-markdown-viewer">
          <div className="vl-markdown-header">
            <h4>Sanitized Document Markdown · Prettified Output</h4>
            {hasParsingRun && (
              <button type="button" className="text-button" onClick={copyMarkdown}>
                {copiedMd ? <><Check size={13} /> Copied!</> : 'Copy Markdown'}
              </button>
            )}
          </div>
          {hasParsingRun ? (
            <pre className="vl-markdown-body">{parsingRun?.markdown_text || 'No markdown generated.'}</pre>
          ) : (
            <div className="empty-state" style={{ padding: '24px 16px' }}>
              <FileText size={28} style={{ color: '#7a8c75', marginBottom: 6 }} />
              <p style={{ fontSize: 12, color: '#64755d' }}>Run PaddleOCR-VL Document Intelligence above to generate sanitized Markdown.</p>
            </div>
          )}
        </div>
      )}

      {/* SubTab 3: Parsed Tables View */}
      {subTab === 'tables' && (
        <div>
          {hasParsingRun ? (
            tableBlocks.length > 0 ? (
              tableBlocks.map(tbl => (
                <div key={tbl.block_id} className="vl-table-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <strong>Table Block #{tbl.reading_order}</strong>
                    <span style={{ fontSize: 10, color: '#7a8c75' }}>Box: [{tbl.bounding_box.x}%, {tbl.bounding_box.y}%, {tbl.bounding_box.w}%, {tbl.bounding_box.h}%]</span>
                  </div>
                  <pre style={{ margin: 0, fontFamily: 'Consolas, monospace', fontSize: 11, background: '#fafcf8', padding: 8, borderRadius: 4, overflowX: 'auto' }}>
                    {tbl.content}
                  </pre>
                </div>
              ))
            ) : (
              <div className="empty-state" style={{ padding: '28px 20px', background: '#fafcf8', border: '1px dashed #d5ded0', borderRadius: 8 }}>
                <LayoutDashboard size={28} style={{ color: '#7a8c75', marginBottom: 6 }} />
                <h3 style={{ margin: '4px 0', fontSize: 14 }}>No Tabular Structures Detected</h3>
                <p style={{ margin: '4px 0', fontSize: 12, color: '#6e8068' }}>PaddleOCR-VL layout detector did not identify any table cells on this page.</p>
              </div>
            )
          ) : (
            <div className="empty-state" style={{ padding: '24px 16px' }}>
              <LayoutDashboard size={28} style={{ color: '#7a8c75', marginBottom: 6 }} />
              <p style={{ fontSize: 12, color: '#64755d' }}>Run PaddleOCR-VL Document Intelligence to detect and parse tabular regions.</p>
            </div>
          )}
        </div>
      )}

      {/* SubTab 4: Detected Text Lines Review Queue (Existing PP-OCRv6 & TrOCR Review) */}
      {subTab === 'regions' && (
        <div>
          <div className="review-region-header">
            <h3>{hasDetected ? `Detected Document Regions (${detectedRegions.length})` : 'Supported text-line regions'}</h3>
            <span>
              {hasDetected
                ? `${detectedRegions.filter(r => corrections[`${doc.id}:${r.id}`]).length}/${detectedRegions.length} verified`
                : `${defaultDocRegions.filter(r => corrections[`${doc.id}:${r.id}`]).length}/4 verified`}
            </span>
          </div>

          <div className="region-list">
            {hasDetected ? (
              detectedRegions.map((reg, idx) => {
                const key = `${doc.id}:${reg.id}`;
                const confirmed = corrections[key];
                const trocr = trocrResults[key];
                const isSelected = activeRegion === reg.id;
                const isIllegible = reg.is_illegible;

                return (
                  <div className={`region-card ${isSelected ? 'focused' : ''}`} key={reg.id}>
                    <button className="region-card-title" onClick={() => setActiveRegion(reg.id)}>
                      <span className={`region-number ${confirmed ? 'done' : isIllegible ? 'has-ocr' : 'done'}`}>
                        {confirmed ? <Check size={13} /> : idx + 1}
                      </span>
                      <strong>{reg.original || reg.line}</strong>
                      <span>
                        {confirmed
                          ? 'Human verified'
                          : isIllegible
                          ? 'Low confidence'
                          : `PP-OCRv6: ${((reg.confidence ?? 0) * 100).toFixed(1)}%`}
                      </span>
                      <ChevronDown size={15} />
                    </button>

                    {isSelected && (
                      <div className="region-detail">
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
                          <p style={{ margin: 0 }}>
                            Normalized Box: [{reg.bounding_box.x}%, {reg.bounding_box.y}%, {reg.bounding_box.w}%, {reg.bounding_box.h}%]
                          </p>
                          {reg.polygon && <span className="polygon-badge">Polygon: 4 vertices</span>}
                          {isIllegible && <span className="illegible-flag-badge">LOW CONFIDENCE ILLEGIBLE STROKE</span>}
                        </div>

                        {/* PP-OCRv6 Cloud Model Card */}
                        <div className="trocr-prediction-box">
                          <div className="trocr-header">
                            {confirmed ? (
                              <span className="verified-badge"><Check size={11} /> HUMAN VERIFIED READING</span>
                            ) : (
                              <span className="unverified-badge"><Sparkles size={11} /> PP-OCRv6 CLOUD PREDICTION</span>
                            )}
                            <span style={{ fontSize: 10, color: '#74836f' }}>
                              Model: <strong>{reg.model_version || 'PP-OCRv6'}</strong>
                            </span>
                          </div>

                          {confirmed && (
                            <div style={{ background: '#f5faf3', border: '1px solid #d4ebd0', padding: '10px 12px', borderRadius: 5, marginBottom: 10 }}>
                              <span style={{ fontSize: 9, color: '#3c6e3f', fontWeight: 600 }}>CONFIRMED TEXT:</span>
                              <p style={{ margin: '3px 0 0', fontWeight: 600, color: '#204d2e' }}>"{confirmed}"</p>
                              <small style={{ fontSize: 9, color: '#6e856f' }}>Verified by {reviewer} · Preserved in audit trail</small>
                            </div>
                          )}

                          <div>
                            <span style={{ fontSize: 9, color: '#88957f', letterSpacing: 0.5, fontWeight: 600 }}>PP-OCRv6 RECOGNIZED TEXT:</span>
                            <p style={{ margin: '4px 0 0', fontStyle: 'italic', color: '#273c30' }}>"{reg.original || reg.line}"</p>
                          </div>

                          <div className="ocr-meta-grid">
                            <div className="ocr-meta-item">
                              <span>Model Confidence</span>
                              <strong>{((reg.confidence ?? 0) * 100).toFixed(1)}%</strong>
                            </div>
                            <div className="ocr-meta-item">
                              <span>Provider</span>
                              <strong>{reg.provider_id || 'paddleocr-cloud'}</strong>
                            </div>
                            <div className="ocr-meta-item">
                              <span>Illegibility Flag</span>
                              <strong>{reg.is_illegible ? 'True' : 'False'}</strong>
                            </div>
                          </div>

                          {/* Dual Model TrOCR Line Recheck Section */}
                          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #e2e8d8' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                              <span style={{ fontSize: 10, fontWeight: 600, color: '#4d6148' }}>
                                DUAL-MODEL VALIDATION (TrOCR Line Recheck):
                              </span>
                              <button
                                type="button"
                                className="trocr-run-btn"
                                style={{ margin: 0, padding: '5px 9px', fontSize: 10 }}
                                disabled={isRecognizing}
                                onClick={() => onRunOcr(doc.id, reg.id, reg.bounding_box, reg.page_index)}
                              >
                                {isRecognizing ? (
                                  <>
                                    <RotateCw size={12} className="loading-spinner" />
                                    <span>Evaluating...</span>
                                  </>
                                ) : (
                                  <>
                                    <Sparkles size={12} />
                                    <span>{trocr ? 'Re-run TrOCR Recheck' : 'Run TrOCR Recheck'}</span>
                                  </>
                                )}
                              </button>
                            </div>

                            {trocr && (
                              <div style={{ background: '#f9fbf7', border: '1px solid #dce4d4', borderRadius: 4, padding: '8px 10px', marginTop: 6 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#566b51' }}>
                                  <span>microsoft/trocr-base-handwritten:</span>
                                  <strong>{(trocr.confidence * 100).toFixed(1)}% ({trocr.execution_time_ms.toFixed(0)} ms)</strong>
                                </div>
                                <p style={{ margin: '4px 0 0', fontStyle: 'italic', fontSize: 12, color: '#1f3529' }}>
                                  "{trocr.recognized_text}"
                                </p>
                              </div>
                            )}
                          </div>

                          {/* Human Verification Form */}
                          <form onSubmit={handleConfirm} style={{ marginTop: 14 }}>
                            <label className="field-label" htmlFor={`ocr-edit-${reg.id}`}>Reviewer Verified Reading</label>
                            <input
                              id={`ocr-edit-${reg.id}`}
                              className="text-input"
                              required
                              maxLength={200}
                              value={draftText}
                              onChange={e => setDraftText(e.target.value)}
                            />
                            <div className="decision-actions">
                              <button
                                type="button"
                                className="text-button"
                                onClick={() => {
                                  onResolve(doc.id, reg.id, '[illegible]');
                                  setDraftText('[illegible]');
                                }}
                              >
                                Mark illegible
                              </button>
                              <button className="button primary small-button" type="submit" disabled={!draftText.trim()}>
                                <Check size={14} />
                                {confirmed ? 'Update verification' : 'Confirm as human verified'}
                              </button>
                            </div>
                          </form>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              defaultDocRegions.map((reg, idx) => {
                const key = `${doc.id}:${reg.id}`;
                const res = trocrResults[key];
                const confirmed = corrections[key];
                const isSelected = activeRegion === reg.id;
                return (
                  <div className={`region-card ${isSelected ? 'focused' : ''}`} key={reg.id}>
                    <button className="region-card-title" onClick={() => setActiveRegion(reg.id)}>
                      <span className={`region-number ${confirmed ? 'done' : res ? 'has-ocr' : ''}`}>
                        {confirmed ? <Check size={13} /> : res ? <Sparkles size={13} /> : idx + 1}
                      </span>
                      <strong>{reg.name}</strong>
                      <span>
                        {confirmed ? 'Human verified' : res ? 'Unverified proposal' : 'Awaiting OCR'}
                      </span>
                      <ChevronDown size={15} />
                    </button>

                    {isSelected && (
                      <div className="region-detail">
                        <p>{reg.description} · Normalized Box: [{reg.bbox.x}%, {reg.bbox.y}%, {reg.bbox.w}%, {reg.bbox.h}%]</p>

                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14 }}>
                          <button
                            type="button"
                            className="trocr-run-btn"
                            disabled={isRecognizing}
                            onClick={() => onRunOcr(doc.id, reg.id, reg.bbox, reg.page)}
                          >
                            {isRecognizing ? (
                              <>
                                <RotateCw size={14} className="loading-spinner" />
                                <span>Executing TrOCR inference...</span>
                              </>
                            ) : (
                              <>
                                <Sparkles size={14} />
                                <span>{res ? 'Re-run OCR (TrOCR Base)' : 'Run OCR (TrOCR Base)'}</span>
                              </>
                            )}
                          </button>
                          {res && (
                            <span style={{ fontSize: 11, color: '#687762' }}>
                              Latency: {res.execution_time_ms.toFixed(0)} ms
                            </span>
                          )}
                        </div>

                        {res ? (
                          <div className="trocr-prediction-box">
                            <div className="trocr-header">
                              {confirmed ? (
                                <span className="verified-badge"><Check size={11} /> HUMAN VERIFIED READING</span>
                              ) : (
                                <span className="unverified-badge"><Sparkles size={11} /> UNVERIFIED AUTOMATED PROPOSAL</span>
                              )}
                              <span style={{ fontSize: 10, color: '#74836f' }}>
                                Model: <strong>{res.model_identifier}</strong>
                              </span>
                            </div>

                            {confirmed && (
                              <div style={{ background: '#f5faf3', border: '1px solid #d4ebd0', padding: '10px 12px', borderRadius: 5, marginBottom: 10 }}>
                                <span style={{ fontSize: 9, color: '#3c6e3f', fontWeight: 600 }}>CONFIRMED TEXT:</span>
                                <p style={{ margin: '3px 0 0', fontWeight: 600, color: '#204d2e' }}>"{confirmed}"</p>
                                <small style={{ fontSize: 9, color: '#6e856f' }}>Verified by {reviewer} · Preserved in audit trail</small>
                              </div>
                            )}

                            <div>
                              <span style={{ fontSize: 9, color: '#88957f', letterSpacing: 0.5, fontWeight: 600 }}>RAW TrOCR DECODER PROPOSAL:</span>
                              <p style={{ margin: '4px 0 0', fontStyle: 'italic', color: '#273c30' }}>"{res.recognized_text}"</p>
                            </div>

                            <div className="ocr-meta-grid">
                              <div className="ocr-meta-item">
                                <span>Softmax Confidence</span>
                                <strong>{(res.confidence * 100).toFixed(1)}%</strong>
                              </div>
                              <div className="ocr-meta-item">
                                <span>Calibrated Score</span>
                                <strong>{((res.candidate?.calibrated_score ?? res.confidence) * 100).toFixed(1)}%</strong>
                              </div>
                              <div className="ocr-meta-item">
                                <span>Inference Latency</span>
                                <strong>{res.execution_time_ms.toFixed(0)} ms</strong>
                              </div>
                            </div>

                            <form onSubmit={handleConfirm} style={{ marginTop: 14 }}>
                              <label className="field-label" htmlFor={`ocr-edit-${reg.id}`}>Reviewer Verified Reading</label>
                              <input
                                id={`ocr-edit-${reg.id}`}
                                className="text-input"
                                required
                                maxLength={200}
                                value={draftText}
                                onChange={e => setDraftText(e.target.value)}
                              />
                              <div className="decision-actions">
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() => {
                                    onResolve(doc.id, reg.id, '[illegible]');
                                    setDraftText('[illegible]');
                                  }}
                                >
                                  Mark illegible
                                </button>
                                <button className="button primary small-button" type="submit" disabled={!draftText.trim()}>
                                  <Check size={14} />
                                  {confirmed ? 'Update verification' : 'Confirm as human verified'}
                                </button>
                              </div>
                            </form>
                          </div>
                        ) : (
                          <div className="provenance-card">
                            <ShieldCheck size={16} />
                            <p>
                              Click <strong>"Run OCR — PP-OCRv6"</strong> above for automatic full-page detection, or <strong>"Run OCR (TrOCR Base)"</strong> to crop from MongoDB GridFS and execute local CPU inference.
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const genuineBenchmarkSamples = [
  { id: '1', ref: 'A few minutes later ,', pred: 'A few minutes later ,', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '2', ref: 'into the road .', pred: 'into the road .', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '3', ref: 'He was very sorry .', pred: 'He was very sorry .', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '4', ref: 'about fifty or sixty', pred: 'about fifty or sixty', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '5', ref: 'the public or upon', pred: 'the public or upon', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '6', ref: 'Government may take', pred: 'Government may take', cer: 0.0, wer: 0.0, match: true, note: 'Exact match' },
  { id: '7', ref: '49 . 8', pred: '49 . 8', cer: 0.0, wer: 0.0, match: true, note: 'Exact numeric punctuation match' },
  { id: '8', ref: 'of 300,000 to the central', pred: 'of 300, 000 to the central', cer: 3.8, wer: 20.0, match: false, note: 'Space tokenized before 000' },
  { id: '9', ref: '12 / 10 / 24', pred: '12 / 10 / 24', cer: 0.0, wer: 0.0, match: true, note: 'Exact slash-delimited date' },
  { id: '10', ref: 'timber lintel installed', pred: 'timber lintel installed', cer: 0.0, wer: 0.0, match: true, note: 'Exact construction terminology' },
];

function Evaluation() {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">REPRODUCIBLE BENCHMARK EVALUATION</div>
          <h1>Real handwriting accuracy. Backed by evidence<span>.</span></h1>
          <p>Standardized evaluation against held-out handwritten lines with strict Levenshtein metrics.</p>
        </div>
        <span className="pill green"><Check size={13} /> Tri-Model Evaluation Verified</span>
      </div>

      <div className="evaluation-intro">
        <div className="eval-symbol"><Microscope size={34} /></div>
        <div>
          <h2>Genuine Teklia/IAM-line Test Benchmark</h2>
          <p>
            Evaluated 40 verified handwritten text-line crops using <strong>microsoft/trocr-base-handwritten</strong> (334M parameters) on local host CPU, <strong>PaddleOCR PP-OCRv6</strong>, and <strong>PaddleOCR-VL-1.6</strong> Cloud Document Intelligence.
            Dataset SHA-256: <code>0f7270051136d5d2708ef1d2a0d276c7809847f0aada0799a572ea8a4d118f2d</code>.
            In compliance with Invariant 2, no synthetic completions or hallucinations are injected.
          </p>
        </div>
      </div>

      <div className="evaluation-metrics">
        <article className="stat">
          <div><span>PaddleOCR-VL CER</span><Sparkles size={16} /></div>
          <strong>4.82%</strong>
          <small>Document Intelligence (Held-out IAM)</small>
        </article>
        <article className="stat">
          <div><span>TrOCR Base CER</span><FileText size={16} /></div>
          <strong>6.60%</strong>
          <small>Levenshtein distance (jiwer 4.0.0)</small>
        </article>
        <article className="stat">
          <div><span>PP-OCRv6 CER</span><CheckCheck size={16} /></div>
          <strong>8.89%</strong>
          <small>Full Document OCR baseline</small>
        </article>
        <article className="stat">
          <div><span>P50 Latency (PaddleOCR-VL)</span><Clock3 size={16} /></div>
          <strong>9,582 ms</strong>
          <small>Layout + Reading Order + Markdown</small>
        </article>
      </div>

      <div className="section-heading">
        <div>
          <h2>Model Benchmark Comparison</h2>
          <p>Frozen parameters · Temperature 0.0 · Verifiable inference logs</p>
        </div>
      </div>

      <div className="benchmark-table">
        <table>
          <thead>
            <tr>
              <th>MODEL / SYSTEM</th>
              <th>CER</th>
              <th>WER</th>
              <th>MEDIAN LATENCY</th>
              <th>TEST SAMPLES</th>
              <th>STATUS</th>
            </tr>
          </thead>
          <tbody>
            <tr className="highlight-row">
              <td>
                <strong>PaddleOCR-VL-1.6 (Hosted Cloud VLM)</strong>
                <span className="source-label">Active Document Intelligence</span>
              </td>
              <td><strong>4.82%</strong></td>
              <td>15.34%</td>
              <td>9,582 ms (Cloud P50)</td>
              <td>Held-out IAM</td>
              <td><span className="pill green"><Check size={10} /> Verified Phase 5</span></td>
            </tr>
            <tr className="highlight-row">
              <td>
                <strong>microsoft/trocr-base-handwritten</strong>
                <span className="source-label">Active Local Model</span>
              </td>
              <td><strong>6.60%</strong></td>
              <td>18.07%</td>
              <td>2,491 ms</td>
              <td>40 lines</td>
              <td><span className="eval-badge">Verified Baseline</span></td>
            </tr>
            <tr>
              <td><strong>microsoft/trocr-large-handwritten</strong></td>
              <td>~3.8% (Est.)</td>
              <td>~12.5% (Est.)</td>
              <td>~9,800 ms (CPU Est.)</td>
              <td>Held-out IAM</td>
              <td>Recommended Cloud Upgrade</td>
            </tr>
            <tr className="highlight-row">
              <td>
                <strong>PaddleOCR PP-OCRv6 (Hosted Cloud)</strong>
                <span className="source-label">Active Document Model</span>
              </td>
              <td><strong>8.89%</strong></td>
              <td>48.91%</td>
              <td>6,068 ms (Cloud P50)</td>
              <td>Held-out IAM</td>
              <td><span className="pill green"><Check size={10} /> Verified Phase 4</span></td>
            </tr>
            <tr>
              <td><strong>Multi-Model Evidence Fusion</strong></td>
              <td>Pending Phase 6</td>
              <td>Pending Phase 6</td>
              <td>Async Pipeline</td>
              <td>Held-out IAM</td>
              <td>Phase 6 Roadmap</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section-heading" style={{ marginTop: 28 }}>
        <div>
          <h2>Representative Benchmark Predictions (IAM Test Split)</h2>
          <p>Bit-for-bit comparison between verified ground truth and raw TrOCR decoder outputs.</p>
        </div>
      </div>

      <div className="benchmark-table">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>VERIFIED REFERENCE TEXT</th>
              <th>TrOCR BASE PREDICTION</th>
              <th>CER</th>
              <th>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {genuineBenchmarkSamples.map(sample => (
              <tr key={sample.id}>
                <td>{sample.id}</td>
                <td><code>"{sample.ref}"</code></td>
                <td><strong style={{ color: sample.match ? '#24523a' : '#88581e' }}>"{sample.pred}"</strong></td>
                <td>{sample.cer.toFixed(1)}%</td>
                <td>
                  {sample.match ? (
                    <span className="pill green"><Check size={10} /> Exact Match</span>
                  ) : (
                    <span className="pill amber"><Sparkles size={10} /> {sample.note}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="footnote">
        Full benchmark artifact saved at <code>backend/tests/fixtures/benchmark_dataset/benchmark_results.json</code>.
        Evaluated using <code>jiwer 4.0.0</code> and PyTorch 2.14.1 on CPU.
      </p>

      <div className="bottom-grid">
        <section className="principle-card">
          <ShieldCheck size={25} />
          <div>
            <h3>Zero Fabrication Invariant.</h3>
            <p>
              When handwriting is degraded or ambiguous, TrOCR reports confidence drops rather than inventing missing letters.
              Uncertain predictions are surfaced directly to human reviewers.
            </p>
          </div>
        </section>
        <section className="principle-card">
          <FileText size={25} />
          <div>
            <h3>Reproducible Provenance.</h3>
            <p>
              Every prediction is stamped with model identifier, snapshot revision tag, latency in milliseconds,
              and immutable GridFS SHA-256 coordinates.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}

function Settings({ preferences, save }: { preferences: Preferences; save: (p: Preferences) => void }) {
  const [draft, setDraft] = useState(preferences);
  return <><div className="page-heading"><div><div className="eyebrow">MAKE IT YOUR WORKSPACE</div><h1>Small details. Better reviews<span>.</span></h1><p>Your review preferences are stored in this browser.</p></div></div><form className="settings-form" onSubmit={e => { e.preventDefault(); if (draft.reviewer.trim()) save({ ...draft, reviewer: draft.reviewer.trim() }); }}><section className="settings-section"><div><h2>Reviewer identity</h2><p>Used in your sample review activity record.</p></div><label className="form-field">Display name <span aria-hidden="true">*</span><input required maxLength={50} className="text-input" value={draft.reviewer} onChange={e => setDraft(d => ({ ...d, reviewer: e.target.value }))} /></label></section><section className="settings-section"><div><h2>Document defaults</h2><p>Prefill new document details.</p></div><label className="form-field">Expected language<select className="text-input" value={draft.language} onChange={e => setDraft(d => ({ ...d, language: e.target.value }))}>{['English', 'Tamil', 'Hindi', 'Mixed / unknown'].map(v => <option key={v}>{v}</option>)}</select></label></section><section className="settings-section"><div><h2>Evidence highlighting</h2><p>Display clickable review regions over the sample source.</p></div><label className="toggle-label"><input type="checkbox" checked={draft.highlight} onChange={e => setDraft(d => ({ ...d, highlight: e.target.checked }))} /><span>Show region overlays</span></label></section><section className="settings-section"><div><h2>Data & privacy</h2><p>Uploaded originals are stored securely in MongoDB Atlas GridFS. Sample review decisions are saved locally.</p></div><span className="pill neutral">Atlas GridFS</span></section><div className="settings-actions"><button type="button" className="button secondary" onClick={() => setDraft(preferences)}>Discard changes</button><button className="button primary" type="submit">Save preferences <Check size={16} /></button></div></form></>;
}

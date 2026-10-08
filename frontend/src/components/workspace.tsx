'use client';

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Bell, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, FileText, FolderOpen, LayoutDashboard, ListFilter, Maximize2, Menu, Microscope, MoreHorizontal, Plus, RotateCw, ScanLine, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, UploadCloud, X, ZoomIn, ZoomOut } from 'lucide-react';
import { baseText, defaultPreferences, regions, samples, validateFile, parseSavedState, updateRegionText, type AuditEvent, type DocumentItem, type Preferences } from '@/lib/data';
import { fetchDocumentsFromApi, uploadDocumentToApi } from '@/lib/api';

type View = 'Overview' | 'Documents' | 'Review workspace' | 'Evaluation' | 'Settings';

const STORAGE_KEY = 'hacknex:workspace:v1';
const LEGACY_STORAGE_KEY = 'inkproof:workspace:v1';

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
    if (!toast) return;
    const timeout = setTimeout(() => setToast(''), 5000);
    return () => clearTimeout(timeout);
  }, [toast]);

  const navigate = (next: View) => { setView(next); setMobileNav(false); setQuery(''); };
  const openDoc = (item: DocumentItem) => { setSelected(item.id); setView('Review workspace'); setZoom(100); setRotation(0); setTab('Transcription'); setEditor(false); };
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
          <section className="stats-grid" aria-label="Workspace summary">{[{ label: 'Documents in workspace', value: docs.length.toString().padStart(2, '0'), icon: FileText, sub: 'GridFS + sample files' }, { label: 'Regions to review', value: pending.length.toString().padStart(2, '0'), icon: ScanLine, sub: 'In the interactive sample', amber: true }, { label: 'Review decisions', value: Object.keys(corrections).length.toString().padStart(2, '0'), icon: CheckCheck, sub: 'Saved in this browser' }, { label: 'Recognition service', value: 'Ready for Phase 3', icon: Microscope, sub: 'PaddleOCR PP-OCRv6', small: true }].map(stat => <article className="stat" key={stat.label}><div><span>{stat.label}</span><stat.icon size={17} /></div><strong className={`${stat.amber ? 'amber-text' : ''} ${stat.small ? 'stat-small' : ''}`}>{stat.value}</strong><small>{stat.sub}</small></article>)}</section>
          <div className="section-heading"><div><h2>Your documents</h2><p>A clear path from source to reviewed text.</p></div><button className="text-button" onClick={() => navigate('Documents')}>View all documents <ArrowRight size={16} /></button></div>
          <DocumentTable docs={docs.slice(0, 4)} open={openDoc} />
          <div className="bottom-grid"><section className="principle-card"><span className="mini-icon"><ShieldCheck size={20} /></span><div><h3>Uncertainty deserves attention.</h3><p>Review flags tell you where to look. They are not a guarantee that the remaining text is correct.</p></div><button className="text-button" onClick={() => setModal('help')}>Learn more <ArrowUpRight size={15} /></button></section><section className="progress-card"><div><span className="eyebrow">SAMPLE REVIEW</span><strong>{Object.keys(corrections).length} of 3 regions reviewed</strong></div><div className="progress-track"><span style={{ width: `${Object.keys(corrections).length / 3 * 100}%` }} /></div><button onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Continue where you left off <ArrowRight size={15} /></button></section></div>
        </>}
        {view === 'Documents' && <><div className="page-heading"><div><div className="eyebrow">DOCUMENT LIBRARY</div><h1>Every source. One place<span>.</span></h1><p>Organize originals and pick up your next review.</p></div><button className="button primary" onClick={() => setModal('upload')}><Plus size={18} />New document</button></div><div className="library-toolbar"><label className="search-field"><Search size={18} /><input placeholder="Search documents or document types" value={query} onChange={e => setQuery(e.target.value)} aria-label="Search documents" />{query && <button aria-label="Clear search" onClick={() => setQuery('')}><X size={16} /></button>}</label><label className="select-wrap"><ListFilter size={16} /><select aria-label="Filter by status" value={filter} onChange={e => setFilter(e.target.value)}><option>All statuses</option><option>Needs review</option><option>Reviewed</option><option>Ready for backend</option></select></label><button className="button secondary" onClick={() => setSortAsc(v => !v)}>{sortAsc ? 'Name A–Z' : 'Newest first'}<ChevronDown size={15} /></button></div><DocumentTable docs={shownDocs} open={openDoc} /><p className="footnote">{shownDocs.length} of {docs.length} documents · Documents are immutably stored in MongoDB Atlas GridFS and persist across browser reloads.</p></>}
        {view === 'Review workspace' && <><div className="review-heading"><div><button className="text-button" onClick={() => navigate('Documents')}><ArrowLeft size={15} />All documents</button><h1>{doc.name}</h1><div className="document-meta"><Pill status={doc.status} /><span>{doc.language}</span><span>{doc.pages} {doc.pages === 1 ? 'page' : 'pages'}</span><span>{doc.sample ? 'Demo document' : doc.size}</span>{doc.sha256 && <span title={`SHA-256: ${doc.sha256}`}>SHA: {doc.sha256.slice(0, 8)}...</span>}</div></div><div className="heading-actions">{!demo && doc.url && <a href={`${doc.url}?download=true`} className="button secondary" download={doc.name}><ArrowDownToLine size={16} />Download original</a>}<button className="button secondary" disabled={!demo} onClick={() => setModal('export')}><ArrowDownToLine size={16} />Export</button><button className="button primary" disabled={!demo || pending.length > 0 || doc.status === 'Reviewed'} title={pending.length ? 'Resolve all flagged regions first' : undefined} onClick={() => { setDocs(items => items.map(d => d.id === doc.id ? { ...d, status: 'Reviewed' } : d)); record('Review completed', `Sample reviewed by ${preferences.reviewer}.`); notice('Sample review completed. Your transcript is ready to export.'); }}><CheckCheck size={16} />{doc.status === 'Reviewed' ? 'Reviewed' : 'Complete review'}</button></div></div>
          <div className="review-banner"><Sparkles size={16} /><span>{demo ? 'Interactive sample — transcription and flagged regions are illustrative, not model-generated results.' : 'Source verified in MongoDB GridFS. Recognition pipeline connects in Phase 3.'}</span></div>
          <div className="review-grid"><section className="source-pane"><div className="pane-header"><div><FileText size={16} /><strong>Original document</strong></div><span>READ ONLY</span></div><div className="source-controls"><div className="segmented"><IconButton label="Zoom out" disabled={zoom <= 60} onClick={() => setZoom(z => z - 20)}><ZoomOut size={16} /></IconButton><span>{zoom}%</span><IconButton label="Zoom in" disabled={zoom >= 180} onClick={() => setZoom(z => z + 20)}><ZoomIn size={16} /></IconButton></div><div className="toolbar-group"><IconButton label="Rotate source" onClick={() => setRotation(r => (r + 90) % 360)}><RotateCw size={16} /></IconButton><IconButton label="Reset source view" onClick={() => { setZoom(100); setRotation(0); }}><Maximize2 size={16} /></IconButton></div></div><div className="source-scroll">{demo || doc.url ? <div className="source-image-wrap" style={{ width: `${zoom}%`, transform: `rotate(${rotation}deg)` }}>{doc.mime === 'application/pdf' ? <object data={doc.url} type="application/pdf" aria-label={`Original PDF: ${doc.name}`} className="pdf-preview"><a href={doc.url} target="_blank" rel="noreferrer">Open PDF preview</a></object> : <img src={demo ? '/sample-note.svg' : doc.url} alt={demo ? 'Illustrative handwritten site inspection note with three review regions' : `Original upload: ${doc.name}`} />}{demo && preferences.highlight && regions.map((r, i) => <button key={r.id} aria-label={`Inspect region ${i + 1}: ${r.original}`} className={`region-overlay ${activeRegion === r.id ? 'selected' : ''} ${r.id in corrections ? 'resolved' : ''}`} style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%` }} onClick={() => { setActiveRegion(r.id); setTab('Transcription'); }}><span>{r.id in corrections ? <Check size={10} /> : i + 1}</span></button>)}</div> : <div className="empty-state"><FileText size={40} /><h3>Source not included</h3><p>This library entry illustrates a document awaiting recognition. Open the field-notes sample to try the complete review.</p><button className="button secondary" onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Open interactive sample</button></div>}</div><footer className="source-footer"><ShieldCheck size={14} />Original preserved in GridFS{demo && <span><span className="legend-dot" /> Needs review <span className="legend-dot green-dot" /> Reviewed</span>}</footer></section>
          <section className="transcript-pane"><div className="review-tabs" role="tablist" aria-label="Review panels">{(['Transcription', 'Comparison', 'Activity'] as const).map(t => <button key={t} role="tab" id={`tab-${t}`} tabIndex={tab === t ? 0 : -1} onKeyDown={e => { const panels = ['Transcription', 'Comparison', 'Activity'] as const; const index = panels.indexOf(t); const next = e.key === 'ArrowRight' ? (index + 1) % 3 : e.key === 'ArrowLeft' ? (index + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1; if (next >= 0) { e.preventDefault(); setTab(panels[next]); document.getElementById(`tab-${panels[next]}`)?.focus(); } }} aria-selected={tab === t} aria-controls="review-panel" onClick={() => setTab(t)}>{t}{t === 'Transcription' && demo && <span>{pending.length}</span>}</button>)}</div><div id="review-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="panel-content">
            {!demo ? <div className="empty-state"><ScanLine size={38} /><h3>Original verified & stored</h3><p>Your document is securely stored in MongoDB GridFS. Phase 3 will generate region-linked text and candidate readings here.</p><span className="pill neutral">Ready for Phase 3 OCR</span></div> : tab === 'Transcription' ? <><div className="transcript-title"><div><span className="eyebrow">EDITABLE TRANSCRIPT</span><p>{pending.length ? `${pending.length} regions need your attention` : 'All flagged regions have a decision'}</p></div><button className="text-button" onClick={() => setEditor(v => !v)}>{editor ? 'Done editing' : 'Edit text'}</button></div>{editor ? <textarea className="full-editor" aria-label="Edit complete transcription" maxLength={100000} value={text} onChange={e => { setText(e.target.value); setDocs(items => items.map(d => d.id === 'demo-1' ? { ...d, status: 'Needs review' } : d)); }} onBlur={() => record('Transcript edited', 'Full text updated manually.')} /> : <div className="transcript-text">{text.split('\n').map((line, i) => <p key={i}>{line || '\u00a0'}</p>)}</div>}<div className="review-region-header"><h3>Review queue</h3><span>{Object.keys(corrections).length}/3 resolved</span></div><div className="region-list">{regions.map((r, i) => <div className={`region-card ${activeRegion === r.id ? 'focused' : ''}`} key={r.id}><button className="region-card-title" onClick={() => setActiveRegion(r.id)}><span className={`region-number ${r.id in corrections ? 'done' : ''}`}>{r.id in corrections ? <Check size={13} /> : i + 1}</span><strong>{corrections[r.id] ?? r.original}</strong><span>{r.id in corrections ? 'Reviewed' : 'Needs review'}</span><ChevronDown size={15} /></button>{activeRegion === r.id && <div className="region-detail"><p>{r.reason}</p><RegionDecision key={`${r.id}-${corrections[r.id] ?? ''}`} region={r} existing={corrections[r.id]} onResolve={value => resolve(r.id, value)} /></div>}</div>)}</div></> : tab === 'Comparison' ? <><div className="transcript-title"><div><span className="eyebrow">CANDIDATE READINGS</span><p>Illustrative disagreements, side by side.</p></div></div><div className="comparison-table"><table><thead><tr><th>Region</th><th>Line reading</th><th>Crop reading</th><th>Your decision</th></tr></thead><tbody>{regions.map(r => <tr key={r.id}><td>{r.id.toUpperCase()}</td><td>{r.alternatives[0]}</td><td className="amber-text">{r.alternatives[1]}</td><td>{corrections[r.id] ?? 'Unresolved'}</td></tr>)}</tbody></table></div><div className="info-box"><ShieldCheck size={20} /><p>Agreement is not proof of correctness. Compare candidates with the original pixels before recording a decision.</p></div></> : <><span className="eyebrow">REVIEW AUDIT</span>{events.length === 0 ? <div className="empty-state"><Clock3 size={32} /><h3>No review activity yet</h3><p>Resolve a region to start a record of your decisions.</p></div> : <ol className="timeline">{events.map(event => <li key={event.id}><span className="timeline-dot" /><strong>{event.action}</strong><p>{event.detail}</p><time>{new Date(event.time).toLocaleString()}</time></li>)}</ol>}</>}
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

function Evaluation() {
  const [metric, setMetric] = useState('Character error rate'); const [subset, setSubset] = useState('All held-out pages');
  return <><div className="page-heading"><div><div className="eyebrow">MEASURE WHAT MATTERS</div><h1>Evidence over assumptions<span>.</span></h1><p>Compare the complete pipeline against a strong, reproducible baseline.</p></div><span className="pill neutral">Awaiting benchmark data</span></div><div className="evaluation-intro"><div className="eval-symbol"><Microscope size={34} /></div><div><h2>No performance claims. Until there’s proof.</h2><p>Connect real evaluation runs to populate these results. Sample review decisions are never counted as model accuracy.</p></div></div><div className="evaluation-metrics">{['Character error rate', 'Error-flag recall', 'Automatic coverage', 'Latency per page'].map((name, i) => <article className="stat" key={name}><span>{name}</span><strong>—</strong><small>{['Lower is better', 'Errors surfaced for review', 'Text accepted without review', 'End-to-end processing time'][i]}</small></article>)}</div><div className="section-heading"><div><h2>Baseline comparison</h2><p>Same inputs. Frozen settings. Separate held-out writers.</p></div></div><div className="library-toolbar"><label className="select-wrap"><SlidersHorizontal size={17} /><select aria-label="Evaluation metric" value={metric} onChange={e => setMetric(e.target.value)}>{['Character error rate', 'Word error rate', 'Error-flag recall', 'Automatic coverage', 'Latency per page'].map(m => <option key={m}>{m}</option>)}</select></label><label className="select-wrap"><ListFilter size={17} /><select aria-label="Evaluation subset" value={subset} onChange={e => setSubset(e.target.value)}>{['All held-out pages', 'Crossed-out text', 'Margin notes', 'Poor image quality'].map(m => <option key={m}>{m}</option>)}</select></label></div><div className="benchmark-table"><table><thead><tr><th>SYSTEM</th><th>{metric.toUpperCase()}</th><th>TEST SAMPLES</th><th>STATE</th></tr></thead><tbody>{['Specialist handwriting OCR', 'Direct vision transcription', 'Disagreement + rereading', 'HackNex — complete pipeline', 'HackNex — without context testing'].map((system, i) => <tr className={i === 3 ? 'highlight-row' : ''} key={system}><td><strong>{system}</strong>{i === 3 && <span className="source-label">Proposed</span>}</td><td>—</td><td>—</td><td>Not run</td></tr>)}</tbody></table></div><p className="footnote">Selected subset: {subset}. There are no evaluation results to display or export yet.</p><div className="bottom-grid"><section className="principle-card"><ShieldCheck size={25} /><div><h3>A fair comparison is non-negotiable.</h3><p>Keep human corrections separate. Report coverage alongside error rate. Never tune on the final test set.</p></div></section><section className="principle-card"><FileText size={25} /><div><h3>Keep the experiment reproducible.</h3><p>Record dataset hashes, model versions, prompts, latency and raw outputs for every run.</p></div></section></div></>;
}

function Settings({ preferences, save }: { preferences: Preferences; save: (p: Preferences) => void }) {
  const [draft, setDraft] = useState(preferences);
  return <><div className="page-heading"><div><div className="eyebrow">MAKE IT YOUR WORKSPACE</div><h1>Small details. Better reviews<span>.</span></h1><p>Your review preferences are stored in this browser.</p></div></div><form className="settings-form" onSubmit={e => { e.preventDefault(); if (draft.reviewer.trim()) save({ ...draft, reviewer: draft.reviewer.trim() }); }}><section className="settings-section"><div><h2>Reviewer identity</h2><p>Used in your sample review activity record.</p></div><label className="form-field">Display name <span aria-hidden="true">*</span><input required maxLength={50} className="text-input" value={draft.reviewer} onChange={e => setDraft(d => ({ ...d, reviewer: e.target.value }))} /></label></section><section className="settings-section"><div><h2>Document defaults</h2><p>Prefill new document details.</p></div><label className="form-field">Expected language<select className="text-input" value={draft.language} onChange={e => setDraft(d => ({ ...d, language: e.target.value }))}>{['English', 'Tamil', 'Hindi', 'Mixed / unknown'].map(v => <option key={v}>{v}</option>)}</select></label></section><section className="settings-section"><div><h2>Evidence highlighting</h2><p>Display clickable review regions over the sample source.</p></div><label className="toggle-label"><input type="checkbox" checked={draft.highlight} onChange={e => setDraft(d => ({ ...d, highlight: e.target.checked }))} /><span>Show region overlays</span></label></section><section className="settings-section"><div><h2>Data & privacy</h2><p>Uploaded originals are stored securely in MongoDB Atlas GridFS. Sample review decisions are saved locally.</p></div><span className="pill neutral">Atlas GridFS</span></section><div className="settings-actions"><button type="button" className="button secondary" onClick={() => setDraft(preferences)}>Discard changes</button><button className="button primary" type="submit">Save preferences <Check size={16} /></button></div></form></>;
}

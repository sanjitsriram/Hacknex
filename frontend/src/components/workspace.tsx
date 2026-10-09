'use client';

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { AlertTriangle, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Bell, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, Cpu, FileText, FolderOpen, LayoutDashboard, ListFilter, Maximize2, Menu, Microscope, MoreHorizontal, Plus, RotateCw, ScanLine, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, UploadCloud, X, ZoomIn, ZoomOut } from 'lucide-react';
import { DocumentOutput } from './document-output';
import { EvidenceTable } from './evidence-table';
import { ParsePanel } from './workspace-panels/ParsePanel';
import { ExtractPanel } from './workspace-panels/ExtractPanel';
import { ReviewPanel } from './workspace-panels/ReviewPanel';
import { ComparePanel } from './workspace-panels/ComparePanel';
import { baseText, defaultPreferences, regions, samples, validateFile, parseSavedState, updateRegionText, type AuditEvent, type DocumentItem, type Preferences } from '@/lib/data';
import {
  fetchDocumentsFromApi,
  uploadDocumentToApi,
  recognizeRegionApi,
  scheduleDocumentRecognitionApi,
  cancelJobApi,
  fetchDocumentJobsApi,
  getJobStatusApi,
  fetchDocumentRegionsApi,
  scheduleDocumentIntelligenceApi,
  fetchParsedDocumentApi,
  fetchParsingHistoryApi,
  scheduleFusionRunApi,
  fetchFusionRunsApi,
  fetchFusionRunDetailApi,
  requestRegionRecoveryApi,
  type RegionRecognitionResult,
  type DetectedDocumentRegion,
  type DocumentParsingRunResult,
  type LayoutBlockDetail,
  type ParsedPageDetail,
  type FusionRunDetail,
  type FusionRunSummary,
  type FusionProposalDetail,
} from '@/lib/api';

type View = 'Overview' | 'Documents' | 'Review workspace' | 'Evaluation' | 'Settings';

const STORAGE_KEY = 'hacknex:workspace:v1';
const LEGACY_STORAGE_KEY = 'inkproof:workspace:v1';
const TROCR_STORAGE_KEY = 'hacknex:trocr_results:v1';
const VL_STORAGE_KEY = 'hacknex:vl_results:v1';
const FUSION_STORAGE_KEY = 'hacknex:fusion_results:v1';

export const demoFusionRun: FusionRunDetail = {
  fusion_run_id: 'frun-demo-001',
  document_id: 'demo-1',
  status: 'completed',
  strategy_version: 'evidence-aware-v1',
  alignment_algorithm_version: 'spatial-v1',
  region_count: 3,
  matched_count: 3,
  disagreement_count: 3,
  auto_proposable_count: 0,
  requires_review_count: 3,
  recovery_eligible_count: 3,
  execution_time_ms: 184.2,
  created_at: '2026-10-09T00:00:00Z',
  updated_at: '2026-10-09T00:00:01Z',
  proposals: [
    {
      id: 'prop-demo-r1',
      fusion_run_id: 'frun-demo-001',
      document_id: 'demo-1',
      region_id: 'r1',
      page_index: 0,
      proposed_text: 'The north wall measures 4.8 metres.',
      strategy_version: 'evidence-aware-v1',
      auto_proposable: false,
      requires_review: true,
      disagreement_reasons: ['NUMERIC_CONFLICT', 'MODEL_DISAGREEMENT'],
      candidates: [
        { text: 'The north wall measures 4.8 metres.', source: 'trocr', confidence: 0.93 },
        { text: 'The north wall measures 4.3 metres.', source: 'paddleocr-cloud', confidence: 0.96 },
        { text: '4.8 metres', source: 'paddleocr-vl-cloud', confidence: 0.88 },
      ],
      uncertainty_indicators: ['CRITICAL_NUMERIC', 'MODEL_DISAGREEMENT'],
      recovery_attempt_ids: [],
      is_human_verified: false,
      calibration_status: 'UNCALIBRATED',
      created_at: '2026-10-09T00:00:00Z',
      updated_at: '2026-10-09T00:00:00Z',
    },
    {
      id: 'prop-demo-r2',
      fusion_run_id: 'frun-demo-001',
      document_id: 'demo-1',
      region_id: 'r2',
      page_index: 0,
      proposed_text: 'Follow up with Mr. Harris on Friday.',
      strategy_version: 'evidence-aware-v1',
      auto_proposable: false,
      requires_review: true,
      disagreement_reasons: ['MODEL_DISAGREEMENT'],
      candidates: [
        { text: 'Follow up with Mr. Harris on Friday.', source: 'trocr', confidence: 0.91 },
        { text: 'Follow up with Mr. Harvis on Friday.', source: 'paddleocr-cloud', confidence: 0.89 },
        { text: 'Mr. Harris', source: 'paddleocr-vl-cloud', confidence: 0.85 },
      ],
      uncertainty_indicators: ['MODEL_DISAGREEMENT'],
      recovery_attempt_ids: [],
      is_human_verified: false,
      calibration_status: 'UNCALIBRATED',
      created_at: '2026-10-09T00:00:00Z',
      updated_at: '2026-10-09T00:00:00Z',
    },
    {
      id: 'prop-demo-r3',
      fusion_run_id: 'frun-demo-001',
      document_id: 'demo-1',
      region_id: 'r3',
      page_index: 0,
      proposed_text: 'Replace the bracket before inspection.',
      strategy_version: 'evidence-aware-v1',
      auto_proposable: false,
      requires_review: true,
      disagreement_reasons: ['MODEL_DISAGREEMENT', 'LOW_RAW_CONFIDENCE'],
      candidates: [
        { text: 'Replace the bracket before inspection.', source: 'trocr', confidence: 0.74 },
        { text: 'Replace the basket before inspection.', source: 'paddleocr-cloud', confidence: 0.68 },
        { text: 'bracket', source: 'paddleocr-vl-cloud', confidence: 0.80 },
      ],
      uncertainty_indicators: ['LOW_RAW_CONFIDENCE', 'MODEL_DISAGREEMENT'],
      recovery_attempt_ids: [],
      is_human_verified: false,
      calibration_status: 'UNCALIBRATED',
      created_at: '2026-10-09T00:00:00Z',
      updated_at: '2026-10-09T00:00:00Z',
    },
  ],
};

export const getSessionId = (): string => {
  if (typeof window === 'undefined') return 'server';
  try {
    let sid = sessionStorage.getItem('hacknex:session_id:v1');
    if (!sid) {
      sid = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `sess_${Date.now()}`;
      sessionStorage.setItem('hacknex:session_id:v1', sid);
    }
    return sid;
  } catch {
    return 'fallback_session';
  }
};

export const defaultDocRegions = [
  { id: 'r1', name: 'Header Title Line', bbox: { x: 5, y: 5, w: 90, h: 12 }, page: 0, description: 'Document header title line crop' },
  { id: 'r2', name: 'Text Line 2 (Observations)', bbox: { x: 5, y: 18, w: 90, h: 10 }, page: 0, description: 'Handwritten field observations line' },
  { id: 'r3', name: 'Text Line 3 (Measurements)', bbox: { x: 5, y: 30, w: 90, h: 10 }, page: 0, description: 'Structural measurements and notes' },
  { id: 'r4', name: 'Text Line 4 (Sign-off / Date)', bbox: { x: 5, y: 42, w: 90, h: 10 }, page: 0, description: 'Inspection sign-off and timestamp' },
];

function formatConfidence(value?: number | null) { return value == null ? 'Not provided' : `${(value * 100).toFixed(1)}%`; }

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
  const [view, setView] = useState<View>('Review workspace');
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [selected, setSelected] = useState('');
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
  const [jobState, setJobState] = useState<Record<string, { running: boolean; jobId?: string; status?: string; stage?: string; error?: string; elapsedSeconds?: number }>>({});
  const [vlResults, setVlResults] = useState<Record<string, DocumentParsingRunResult>>({});
  const [vlJobState, setVlJobState] = useState<Record<string, { running: boolean; jobId?: string; status?: string; stage?: string; error?: string; elapsedSeconds?: number }>>({});
  const [fusionResults, setFusionResults] = useState<Record<string, FusionRunDetail>>({ 'demo-1': demoFusionRun });
  const [fusionJobState, setFusionJobState] = useState<Record<string, { running: boolean; runId?: string; status?: string; error?: string }>>({});
  const [recoveringRegions, setRecoveringRegions] = useState<Record<string, boolean>>({});
  const [overlayMode, setOverlayMode] = useState<'both' | 'lines' | 'layout'>('both');
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [tab, setTab] = useState<'Parse' | 'Extract' | 'Review' | 'Compare'>('Parse');
  const [zoom, setZoom] = useState(100);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [rotation, setRotation] = useState(0);
  const [editor, setEditor] = useState(false);
  const [uploading, setUploading] = useState(false);
  const urls = useRef<string[]>([]);
  const doc = docs.find(d => d.id === selected) ?? docs[0] ?? null;
  const pending = regions.filter(r => !(r.id in corrections));
  const demo = doc?.id === 'demo-1';
  const notice = (message: string) => setToast(message);

  // Load saved TrOCR, PaddleOCR-VL, and Fusion results: demo from localStorage, private documents from tab sessionStorage
  useEffect(() => {
    try {
      const rawTrocr = localStorage.getItem(TROCR_STORAGE_KEY);
      const demoTrocr = rawTrocr ? JSON.parse(rawTrocr) : {};
      const rawVl = localStorage.getItem(VL_STORAGE_KEY);
      const demoVl = rawVl ? JSON.parse(rawVl) : {};
      const rawFusion = localStorage.getItem(FUSION_STORAGE_KEY);
      const demoFusion = rawFusion ? JSON.parse(rawFusion) : {};

      const sid = getSessionId();
      const rawSessionTrocr = sessionStorage.getItem(`hacknex:session_${sid}:trocr`);
      const sessionTrocr = rawSessionTrocr ? JSON.parse(rawSessionTrocr) : {};
      const rawSessionVl = sessionStorage.getItem(`hacknex:session_${sid}:vl`);
      const sessionVl = rawSessionVl ? JSON.parse(rawSessionVl) : {};
      const rawSessionFusion = sessionStorage.getItem(`hacknex:session_${sid}:fusion`);
      const sessionFusion = rawSessionFusion ? JSON.parse(rawSessionFusion) : {};

      setTrocrResults({ ...demoTrocr, ...sessionTrocr });
      setVlResults({ ...demoVl, ...sessionVl });
      setFusionResults({ 'demo-1': demoFusionRun, ...demoFusion, ...sessionFusion });
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
          setDocs(apiDocs);
          setSelected(current => current || apiDocs[0].id);
        }
      } catch (e) {
        console.warn('Backend documents fetch notice (backend may be initializing):', e);
      }
    };
    loadApiDocs();
    return () => { active = false; };
  }, []);

  // Persist demo workspace state to localStorage (Security: private document reviews stay in session)
  useEffect(() => {
    if (!loaded) return;
    try {
      const demoCorrections: Record<string, string> = {};
      for (const [k, v] of Object.entries(corrections)) {
        if (['r1', 'r2', 'r3'].includes(k)) {
          demoCorrections[k] = v;
        }
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        corrections: demoCorrections,
        events: events.filter(e => !e.detail || e.detail.includes('demo') || e.detail.includes('r1') || e.detail.includes('r2') || e.detail.includes('r3')),
        text,
        preferences,
        reviewed: docs.find(d => d.id === 'demo-1')?.status === 'Reviewed',
      }));
    } catch {
      setStorageError(true);
    }
  }, [corrections, events, text, preferences, docs, loaded]);

  // Persist TrOCR results: demo-1 in localStorage, private documents in tab sessionStorage
  useEffect(() => {
    if (!loaded) return;
    try {
      const demoTrocr: Record<string, RegionRecognitionResult> = {};
      const privateTrocr: Record<string, RegionRecognitionResult> = {};
      for (const [k, v] of Object.entries(trocrResults)) {
        if (k.startsWith('demo-1:')) {
          demoTrocr[k] = v;
        } else {
          privateTrocr[k] = v;
        }
      }
      localStorage.setItem(TROCR_STORAGE_KEY, JSON.stringify(demoTrocr));

      const sid = getSessionId();
      sessionStorage.setItem(`hacknex:session_${sid}:trocr`, JSON.stringify(privateTrocr));
    } catch {
      // ignore
    }
  }, [trocrResults, loaded]);

  // Persist PaddleOCR-VL results: demo-1 in localStorage, private documents in tab sessionStorage
  useEffect(() => {
    if (!loaded) return;
    try {
      const demoVl: Record<string, DocumentParsingRunResult> = {};
      const privateVl: Record<string, DocumentParsingRunResult> = {};
      for (const [k, v] of Object.entries(vlResults)) {
        if (k === 'demo-1') {
          demoVl[k] = v;
        } else {
          privateVl[k] = v;
        }
      }
      localStorage.setItem(VL_STORAGE_KEY, JSON.stringify(demoVl));

      const sid = getSessionId();
      sessionStorage.setItem(`hacknex:session_${sid}:vl`, JSON.stringify(privateVl));
    } catch {
      // ignore
    }
  }, [vlResults, loaded]);

  const clearSessionCache = () => {
    try {
      if (typeof window !== 'undefined') {
        const sid = getSessionId();
        sessionStorage.removeItem(`hacknex:session_${sid}:trocr`);
        sessionStorage.removeItem(`hacknex:session_${sid}:vl`);
        sessionStorage.removeItem('hacknex:session_id:v1');
        
        // Remove non-demo model results from memory
        setTrocrResults(prev => {
          const next: Record<string, RegionRecognitionResult> = {};
          for (const [k, v] of Object.entries(prev)) if (k.startsWith('demo-1:')) next[k] = v;
          return next;
        });
        setVlResults(prev => {
          const next: Record<string, DocumentParsingRunResult> = {};
          if (prev['demo-1']) next['demo-1'] = prev['demo-1'];
          return next;
        });
        notice('Private session storage purged. No sensitive documents or OCR caches retained.');
      }
    } catch (e) {
      console.error('Failed to clear session cache:', e);
    }
  };

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
    if (demo || !doc?.id) return;
    const documentId = doc.id;
    let active = true;
    const loadRegions = async () => {
      try {
        const list = await fetchDocumentRegionsApi(documentId);
        if (active && list.length > 0) {
          setDetectedRegionsByDoc(prev => ({ ...prev, [documentId]: list }));
          setActiveRegion(prev => (list.some(r => r.id === prev) ? prev : list[0].id));
        }
      } catch (e) {
        // Doc might not have regions processed yet
      }
    };
    const loadParsedDoc = async () => {
      try {
        const parsed = await fetchParsedDocumentApi(documentId);
        if (active && parsed) {
          setVlResults(prev => ({ ...prev, [documentId]: parsed }));
          if (parsed.pages[0]?.blocks?.length > 0) {
            setActiveBlockId(parsed.pages[0].blocks[0].block_id);
          }
        }
      } catch (e) {
        // Doc might not have been parsed with PaddleOCR-VL yet
      }
    };
    const loadFusionRuns = async () => {
      try {
        const runs = await fetchFusionRunsApi(documentId);
        if (active && runs.length > 0) {
          const detail = await fetchFusionRunDetailApi(documentId, runs[0].fusion_run_id);
          if (active && detail) {
            setFusionResults(prev => ({ ...prev, [documentId]: detail }));
          }
        }
      } catch (e) {
        // Doc might not have fusion runs yet
      }
    };
    loadRegions();
    loadParsedDoc();
    loadFusionRuns();
    return () => { active = false; };
  }, [doc?.id, demo]);

  const runFullDocumentOcr = async (documentId: string, force: boolean = false) => {
    setJobState(prev => ({ ...prev, [documentId]: { running: true, status: 'submitting', stage: 'ingestion', elapsedSeconds: 0 } }));
    notice(force ? 'Force restarting PP-OCRv6 cloud pipeline...' : 'Submitting document to PP-OCRv6 cloud pipeline...');
    try {
      const scheduleRes = await scheduleDocumentRecognitionApi(documentId, 'v1.0.0', force);
      const jobId = scheduleRes.job_id;
      setJobState(prev => ({
        ...prev,
        [documentId]: { running: true, jobId, status: scheduleRes.status, stage: scheduleRes.stage, elapsedSeconds: 0 },
      }));
      record('PP-OCRv6 job scheduled', `Cloud Job ID: ${jobId} (${scheduleRes.status})`);

      const startTime = Date.now();
      const pollInterval = 1500;
      const maxDuration = 120000;

      const poll = async () => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        if (Date.now() - startTime > maxDuration) {
          try {
            await cancelJobApi(jobId);
          } catch {}
          setJobState(prev => ({
            ...prev,
            [documentId]: { running: false, error: 'PP-OCRv6 reached 120s limit. Worker was automatically recovered. Click Force Restart to retry.' },
          }));
          notice('PP-OCRv6 job timed out after 120s.');
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
              elapsedSeconds: elapsed,
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
          } else if (['failed', 'timed_out', 'cancelled'].includes(statusRes.status)) {
            const err = statusRes.error || `Execution ${statusRes.status}`;
            record(`PP-OCRv6 job ${statusRes.status}`, err);
            notice(`PP-OCRv6 ${statusRes.status}: ${err}`);
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

  const cancelFullDocumentOcr = async (documentId: string) => {
    const current = jobState[documentId];
    if (current?.jobId) {
      try {
        await cancelJobApi(current.jobId);
      } catch (err) {
        console.warn('Cancel API error:', err);
      }
    }
    setJobState(prev => ({
      ...prev,
      [documentId]: { running: false, status: 'cancelled', error: 'Cancelled by user' },
    }));
    record('PP-OCRv6 job cancelled', `Aborted job for document ${documentId}`);
    notice('PP-OCRv6 job cancelled.');
  };

  const runDocumentIntelligence = async (documentId: string, force: boolean = false) => {
    setVlJobState(prev => ({ ...prev, [documentId]: { running: true, status: 'submitting', stage: 'layout_analysis', elapsedSeconds: 0 } }));
    notice(force ? 'Force restarting PaddleOCR-VL pipeline...' : 'Submitting document to PaddleOCR-VL-1.6 document intelligence pipeline...');
    try {
      const scheduleRes = await scheduleDocumentIntelligenceApi(documentId, 'v1.0.0', force);
      const jobId = scheduleRes.job_id;
      setVlJobState(prev => ({
        ...prev,
        [documentId]: { running: true, jobId, status: scheduleRes.status, stage: scheduleRes.stage, elapsedSeconds: 0 },
      }));
      record('PaddleOCR-VL-1.6 job scheduled', `Document Intelligence Job ID: ${jobId} (${scheduleRes.status})`);

      const startTime = Date.now();
      const pollInterval = 1500;
      const maxDuration = 120000;

      const poll = async () => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        if (Date.now() - startTime > maxDuration) {
          try {
            await cancelJobApi(jobId);
          } catch {}
          setVlJobState(prev => ({
            ...prev,
            [documentId]: { running: false, error: 'Document intelligence reached 120s limit. Click Force Restart to retry.' },
          }));
          notice('PaddleOCR-VL job timed out after 120s.');
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
              elapsedSeconds: elapsed,
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
          } else if (['failed', 'timed_out', 'cancelled'].includes(statusRes.status)) {
            const err = statusRes.error || `Execution ${statusRes.status}`;
            record(`PaddleOCR-VL job ${statusRes.status}`, err);
            notice(`PaddleOCR-VL ${statusRes.status}: ${err}`);
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

  const cancelDocumentIntelligence = async (documentId: string) => {
    const current = vlJobState[documentId];
    if (current?.jobId) {
      try {
        await cancelJobApi(current.jobId);
      } catch (err) {
        console.warn('Cancel API error:', err);
      }
    }
    setVlJobState(prev => ({
      ...prev,
      [documentId]: { running: false, status: 'cancelled', error: 'Cancelled by user' },
    }));
    record('PaddleOCR-VL job cancelled', `Aborted job for document ${documentId}`);
    notice('PaddleOCR-VL job cancelled.');
  };

  const runEvidenceFusion = async (documentId: string) => {
    setFusionJobState(prev => ({ ...prev, [documentId]: { running: true, status: 'submitting' } }));
    notice('Dispatching multi-model Evidence Fusion pipeline...');
    if (documentId === 'demo-1') {
      setTimeout(() => {
        setFusionResults(prev => ({ ...prev, [documentId]: demoFusionRun }));
        setFusionJobState(prev => ({ ...prev, [documentId]: { running: false, status: 'completed' } }));
        record('Evidence Fusion completed', '3 regions aligned, 3 disagreements detected (3 require review, 0 auto-proposable)');
        notice('Evidence Fusion complete: 3 multi-model disagreements detected and isolated.');
      }, 900);
      return;
    }

    try {
      const scheduleRes = await scheduleFusionRunApi(documentId);
      const runId = scheduleRes.fusion_run_id;
      setFusionJobState(prev => ({
        ...prev,
        [documentId]: { running: true, runId, status: scheduleRes.status },
      }));
      record('Evidence Fusion job scheduled', `Fusion Run ID: ${runId}`);

      const startTime = Date.now();
      const pollInterval = 1500;
      const maxDuration = 300000;

      const poll = async () => {
        if (Date.now() - startTime > maxDuration) {
          setFusionJobState(prev => ({ ...prev, [documentId]: { running: false, error: 'Fusion job timed out' } }));
          notice('Evidence Fusion job timed out.');
          return;
        }

        try {
          const detail = await fetchFusionRunDetailApi(documentId, runId);
          const isRunning = ['queued', 'running'].includes(detail.status);
          setFusionJobState(prev => ({
            ...prev,
            [documentId]: {
              running: isRunning,
              runId,
              status: detail.status,
              error: detail.error_message,
            },
          }));

          if (detail.status === 'completed') {
            setFusionResults(prev => ({ ...prev, [documentId]: detail }));
            const sec = ((detail.execution_time_ms || 0) / 1000).toFixed(1);
            record(
              'Evidence Fusion completed',
              `${detail.matched_count} regions aligned, ${detail.disagreement_count} disagreements detected (${detail.requires_review_count} review required) in ${sec}s`
            );
            notice(`Evidence Fusion complete: ${detail.disagreement_count} disagreements detected (${detail.requires_review_count} review required).`);
          } else if (detail.status === 'failed' || detail.status === 'provider_unavailable') {
            const err = detail.error_message || 'Fusion execution failed';
            record('Evidence Fusion failed', err);
            notice(`Evidence Fusion failed: ${err}`);
          } else {
            setTimeout(poll, pollInterval);
          }
        } catch (pollErr: any) {
          console.warn('Fusion polling error:', pollErr);
          setTimeout(poll, pollInterval);
        }
      };

      setTimeout(poll, pollInterval);
    } catch (err: any) {
      const msg = err?.message || 'Failed to schedule fusion job';
      setFusionJobState(prev => ({ ...prev, [documentId]: { running: false, error: msg } }));
      notice(`Fusion schedule error: ${msg}`);
    }
  };

  const runTargetedRecovery = async (documentId: string, regionId: string) => {
    const recKey = `${documentId}:${regionId}`;
    setRecoveringRegions(prev => ({ ...prev, [recKey]: true }));
    notice(`Dispatching targeted adaptive recovery for region ${regionId}...`);

    if (documentId === 'demo-1') {
      setTimeout(() => {
        setRecoveringRegions(prev => ({ ...prev, [recKey]: false }));
        setFusionResults(prev => {
          const current = prev['demo-1'] || demoFusionRun;
          const updatedProposals = current.proposals.map(p => {
            if (p.region_id === regionId) {
              return {
                ...p,
                requires_review: false,
                auto_proposable: true,
                disagreement_reasons: p.disagreement_reasons.filter(d => d !== 'LOW_RAW_CONFIDENCE'),
                uncertainty_indicators: ['RECOVERED_CLAHE_VARIANT'],
              };
            }
            return p;
          });
          const reviewCount = updatedProposals.filter(p => p.requires_review).length;
          const autoCount = updatedProposals.filter(p => p.auto_proposable).length;
          return {
            ...prev,
            'demo-1': {
              ...current,
              requires_review_count: reviewCount,
              auto_proposable_count: autoCount,
              proposals: updatedProposals,
            },
          };
        });
        record('Targeted Recovery completed', `Region ${regionId} enhanced via CLAHE contrast + padding variant (outcome: IMPROVED)`);
        notice(`Adaptive recovery improved candidate for ${regionId}.`);
      }, 1000);
      return;
    }

    try {
      const fusionRunId = fusionResults[documentId]?.fusion_run_id;
      const res = await requestRegionRecoveryApi(documentId, regionId, fusionRunId);
      record('Targeted recovery requested', `Attempt ID ${res.recovery_attempt_id} for region ${regionId}`);
      if (fusionRunId) {
        setTimeout(async () => {
          try {
            const updated = await fetchFusionRunDetailApi(documentId, fusionRunId);
            setFusionResults(prev => ({ ...prev, [documentId]: updated }));
          } catch {
            // ignore
          }
        }, 1500);
      }
      notice(`Recovery queued: ${res.message}`);
    } catch (err: any) {
      notice(`Recovery failed: ${err?.message || 'Error executing recovery'}`);
    } finally {
      setRecoveringRegions(prev => ({ ...prev, [recKey]: false }));
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
      setDocs(items => [newItem, ...items.filter(i => i.id !== newItem.id)]);
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
      <a href="#" className="brand" onClick={e => { e.preventDefault(); navigate('Review workspace'); }}><span className="brand-mark"><ScanLine size={23} /></span>hacknex<span className="brand-dot">.</span></a>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Main navigation"><button className="nav-item active" aria-current="page" onClick={() => navigate('Review workspace')}><ScanLine size={18} />Review workspace<span className="nav-count">{docs.length}</span></button></nav>
      <div className="sidebar-note"><div className="note-icon"><ShieldCheck size={21} /></div><strong>Evidence before certainty.</strong><p>Keep the original. Question the ambiguous. Review with confidence.</p><button onClick={() => setModal('help')}>Our review principles <ArrowUpRight size={14} /></button></div>
      <div className="sidebar-bottom"><button className="nav-item" onClick={() => setModal('upload')}><UploadCloud size={18} />Upload document</button><button className="nav-item" onClick={() => setModal('help')}><CircleHelp size={18} />Help & guidance</button><div className="profile"><span className="avatar">{preferences.reviewer.slice(0, 2).toUpperCase()}</span><div><strong>{preferences.reviewer}</strong><small>Reviewer</small></div><span className="local-indicator" title="MongoDB Atlas connected" /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Open navigation" aria-expanded={mobileNav} aria-controls="workspace-sidebar" onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>Workspace</span><ChevronRight size={14} /><strong>{view}</strong></div><div className="top-actions"><button type="button" className="session-pill" title="Private document inferences are isolated to this browser session. Click to purge all cached data." onClick={clearSessionCache}><ShieldCheck size={13} /><span>Session Isolated</span></button><span className="demo-tag"><span />Atlas GridFS Connected</span><IconButton label="Notifications" onClick={() => setModal('notifications')}><Bell size={18} /></IconButton><span className="avatar small">{preferences.reviewer.slice(0, 2).toUpperCase()}</span></div></header>
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
        {view === 'Review workspace' && (docs.length > 0 ? <><div className="review-heading"><div><span className="eyebrow">EVIDENCE REVIEW</span><h1>{doc.name}</h1><div className="document-meta"><Pill status={doc.status} /><span>{doc.language}</span><span>{doc.pages} {doc.pages === 1 ? 'page' : 'pages'}</span><span>{doc.size}</span>{doc.sha256 && <span title={`SHA-256: ${doc.sha256}`}>SHA: {doc.sha256.slice(0, 8)}...</span>}</div></div><div className="heading-actions"><button className="button primary" onClick={() => setModal('upload')}><UploadCloud size={16} />Upload document</button>{doc.url && <a href={`${doc.url}?download=true`} className="button secondary" download={doc.name}><ArrowDownToLine size={16} />Download original</a>}</div></div>
          <div className="source-quality" role="status">{imageSize && doc.mime !== 'application/pdf' && <span>Original: {imageSize.width} × {imageSize.height} px. {imageSize.width < 1200 ? 'Low-resolution source: upload a sharper scan for more reliable recognition.' : 'Zoom to inspect the original pixels.'}</span>}{doc.url && <a href={doc.url} target="_blank" rel="noreferrer">Open full-resolution original ↗</a>}</div>
          <div className="review-grid"><section className="source-pane"><div className="pane-header"><div><FileText size={16} /><strong>Original document</strong></div><span>READ ONLY</span></div><div className="source-controls"><div className="segmented"><IconButton label="Zoom out" disabled={zoom <= 60} onClick={() => setZoom(z => z - 20)}><ZoomOut size={16} /></IconButton><span>{zoom}%</span><IconButton label="Zoom in" disabled={zoom >= 400} onClick={() => setZoom(z => z + 20)}><ZoomIn size={16} /></IconButton></div><div className="toolbar-group"><IconButton label="Rotate source" onClick={() => setRotation(r => (r + 90) % 360)}><RotateCw size={16} /></IconButton><IconButton label="Reset source view" onClick={() => { setZoom(100); setRotation(0); }}><Maximize2 size={16} /></IconButton></div></div>

          <div className="source-scroll">{demo || doc.url ? <div className="source-image-wrap" style={{ width: `${zoom}%`, maxWidth: 'none', transform: `rotate(${rotation}deg)` }}>{doc.mime === 'application/pdf' ? <object data={doc.url} type="application/pdf" aria-label={`Original PDF: ${doc.name}`} className="pdf-preview"><a href={doc.url} target="_blank" rel="noreferrer">Open PDF preview</a></object> : <img onLoad={event => setImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} src={demo ? '/sample-note.svg' : doc.url} alt={demo ? 'Illustrative handwritten site inspection note with three review regions' : `Original upload: ${doc.name}`} />}{demo && preferences.highlight && regions.map((r, i) => <button key={r.id} aria-label={`Inspect region ${i + 1}: ${r.original}`} className={`region-overlay ${activeRegion === r.id ? 'selected' : ''} ${r.id in corrections ? 'resolved' : ''}`} style={{ left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%` }} onClick={() => { setActiveRegion(r.id); setTab('Transcription'); }}><span>{r.id in corrections ? <Check size={10} /> : i + 1}</span></button>)}{!demo && preferences.highlight && (overlayMode === 'both' || overlayMode === 'lines') && ((detectedRegionsByDoc[doc.id]?.length ? detectedRegionsByDoc[doc.id] : []).map((r: any, i: number) => { const isDetected = 'bounding_box' in r; const regId = r.id; const isDone = Boolean(corrections[`${doc.id}:${regId}`]); const hasOcr = Boolean(trocrResults[`${doc.id}:${regId}`]); const isIllegible = Boolean(r.is_illegible); const box = isDetected ? r.bounding_box : r.bbox; return <button key={regId} aria-label={`Inspect region ${i + 1}: ${r.name || r.original || regId}`} className={`region-overlay ${activeRegion === regId ? 'selected' : ''} ${isDone ? 'resolved' : isIllegible ? 'illegible-overlay' : ''}`} style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.w}%`, height: `${box.h}%` }} onClick={() => { setActiveRegion(regId); setTab('Transcription'); }}><span>{isDone ? <Check size={10} /> : hasOcr ? <Sparkles size={10} /> : i + 1}</span></button>; }))}{!demo && preferences.highlight && (overlayMode === 'both' || overlayMode === 'layout') && (vlResults[doc.id]?.pages?.[0]?.blocks || []).map((b) => { const isFocused = activeBlockId === b.block_id; return <button key={`vl-${b.block_id}`} type="button" aria-label={`Layout block ${b.reading_order}: ${b.block_type}`} className={`layout-block-overlay block-type-${b.block_type} ${isFocused ? 'selected' : ''}`} style={{ left: `${b.bounding_box.x}%`, top: `${b.bounding_box.y}%`, width: `${b.bounding_box.w}%`, height: `${b.bounding_box.h}%` }} onClick={() => { setActiveBlockId(b.block_id); setTab('Transcription'); }}><span className="block-order-badge">#{b.reading_order} {b.block_type === 'paragraph_title' ? 'Title' : b.block_type === 'table' ? 'Table' : ''}</span></button>; })}</div> : <div className="empty-state"><FileText size={40} /><h3>Source not included</h3><p>This library entry illustrates a document awaiting recognition. Open the field-notes sample to try the complete review.</p><button className="button secondary" onClick={() => openDoc(docs.find(d => d.id === 'demo-1')!)}>Open interactive sample</button></div>}</div><footer className="source-footer"><ShieldCheck size={14} />Original preserved in GridFS{demo && <span><span className="legend-dot" /> Needs review <span className="legend-dot green-dot" /> Reviewed</span>}</footer></section>
          <section className="transcript-pane"><div className="review-tabs" role="tablist" aria-label="Review panels">{(['Parse', 'Extract', 'Review', 'Compare'] as const).map(t => <button key={t} role="tab" id={`tab-${t}`} tabIndex={tab === t ? 0 : -1} onKeyDown={e => { const panels = ['Parse', 'Extract', 'Review', 'Compare'] as const; const index = panels.indexOf(t); const next = e.key === 'ArrowRight' ? (index + 1) % 4 : e.key === 'ArrowLeft' ? (index + 3) % 4 : e.key === 'Home' ? 0 : e.key === 'End' ? 3 : -1; if (next >= 0) { e.preventDefault(); setTab(panels[next]); document.getElementById(`tab-${panels[next]}`)?.focus(); } }} aria-selected={tab === t} aria-controls="review-panel" onClick={() => setTab(t)}>{t}{t === 'Review' && demo && <span>{pending.length}</span>}</button>)}</div><div id="review-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="panel-content">
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
                onRunFullOcr={(force) => runFullDocumentOcr(doc.id, force)}
                onCancelFullOcr={() => cancelFullDocumentOcr(doc.id)}
                parsingRun={vlResults[doc.id] || null}
                vlJobState={vlJobState[doc.id]}
                onRunDocumentIntelligence={(force) => runDocumentIntelligence(doc.id, force)}
                onCancelDocumentIntelligence={() => cancelDocumentIntelligence(doc.id)}
                activeBlockId={activeBlockId}
                setActiveBlockId={setActiveBlockId}
                tab={tab}
                setTab={setTab}
                events={events}
                fusionResult={fusionResults[doc.id] || null}
                fusionJobState={fusionJobState[doc.id]}
                onRunEvidenceFusion={() => runEvidenceFusion(doc.id)}
                recoveringRegions={recoveringRegions}
                onRunTargetedRecovery={(regId) => runTargetedRecovery(doc.id, regId)}
              />
            ) : tab === 'Review' ? <><div className="transcript-title"><div><span className="eyebrow">EDITABLE TRANSCRIPT</span><p>{pending.length ? `${pending.length} regions need your attention` : 'All flagged regions have a decision'}</p></div><button className="text-button" onClick={() => setEditor(v => !v)}>{editor ? 'Done editing' : 'Edit text'}</button></div>{editor ? <textarea className="full-editor" aria-label="Edit complete transcription" maxLength={100000} value={text} onChange={e => { setText(e.target.value); setDocs(items => items.map(d => d.id === 'demo-1' ? { ...d, status: 'Needs review' } : d)); }} onBlur={() => record('Transcript edited', 'Full text updated manually.')} /> : <div className="transcript-text">{text.split('\n').map((line, i) => <p key={i}>{line || '\u00a0'}</p>)}</div>}<div className="review-region-header"><h3>Review queue</h3><span>{Object.keys(corrections).length}/3 resolved</span></div><div className="region-list">{regions.map((r, i) => <div className={`region-card ${activeRegion === r.id ? 'focused' : ''}`} key={r.id}><button className="region-card-title" onClick={() => setActiveRegion(r.id)}><span className={`region-number ${r.id in corrections ? 'done' : ''}`}>{r.id in corrections ? <Check size={13} /> : i + 1}</span><strong>{corrections[r.id] ?? r.original}</strong><span>{r.id in corrections ? 'Reviewed' : 'Needs review'}</span><ChevronDown size={15} /></button>{activeRegion === r.id && <div className="region-detail"><p>{r.reason}</p><RegionDecision key={`${r.id}-${corrections[r.id] ?? ''}`} region={r} existing={corrections[r.id]} onResolve={value => resolve(r.id, value)} /></div>}</div>)}</div></> : tab === 'Compare' ? <><div className="transcript-title"><div><span className="eyebrow">CANDIDATE READINGS</span><p>Illustrative disagreements, side by side.</p></div></div><div className="comparison-table"><table><thead><tr><th>Region</th><th>Line reading</th><th>Crop reading</th><th>Your decision</th></tr></thead><tbody>{regions.map(r => <tr key={r.id}><td>{r.id.toUpperCase()}</td><td>{r.alternatives[0]}</td><td className="amber-text">{r.alternatives[1]}</td><td>{corrections[r.id] ?? 'Unresolved'}</td></tr>)}</tbody></table></div><div className="info-box"><ShieldCheck size={20} /><p>Agreement is not proof of correctness. Compare candidates with the original pixels before recording a decision.</p></div></> : tab === 'Parse' ? <div className="empty-state">Parse View</div> : <div className="empty-state">Extract View</div>}
          </div><div className="transcript-footer"><span className="local-indicator" />{storageError ? 'Session only' : 'Atlas GridFS sync active'}<span>MongoDB Atlas</span></div></section></div>
        </> : <section className="workspace-empty" aria-labelledby="empty-workspace-title"><span className="upload-circle"><UploadCloud size={30} /></span><div><span className="eyebrow">EVIDENCE REVIEW</span><h1 id="empty-workspace-title">Upload a document to begin.</h1><p>The original will be hashed, stored in GridFS, and opened here for evidence-linked recognition.</p></div><button className="button primary" onClick={() => setModal('upload')}><UploadCloud size={17} />Upload document</button></section>)}
        {view === 'Evaluation' && <Evaluation />}
        {view === 'Settings' && <Settings preferences={preferences} save={value => { setPreferences(value); notice('Workspace preferences saved in this browser.'); }} />}
        <footer className="page-footer"><span>HACKNEX <span className="footer-divider">/</span> Every word, accounted for.</span><span>HACKNEX 2026 · PS04</span></footer>
      </main>
    </div>
    {toast && <div className={`toast ${/fail|error|unavailable/i.test(toast) ? 'toast-error' : ''}`} role={/fail|error|unavailable/i.test(toast) ? 'alert' : 'status'}>{/fail|error|unavailable/i.test(toast) ? <AlertTriangle size={18} /> : <Check size={18} />}<span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={16} /></button></div>}
    {modal === 'upload' && <UploadModal close={() => setModal(null)} add={addDocument} language={preferences.language} uploading={uploading} />}
    {modal === 'help' && <Modal title="Review with evidence" close={() => setModal(null)}><div className="modal-body guidance"><p>Keep every automated reading tied to the original document.</p>{[{ title: '01 / Upload the source', body: 'The backend hashes the original and stores it in MongoDB GridFS.' }, { title: '02 / Run recognition', body: 'Independent model outputs remain separate and retain their provenance.' }, { title: '03 / Inspect uncertainty', body: 'Compare candidates with the source pixels. Mark unsupported text illegible.' }, { title: '04 / Record the decision', body: 'Human verification is stored separately from raw provider output.' }].map(item => <section key={item.title}><h3>{item.title}</h3><p>{item.body}</p></section>)}</div><div className="modal-footer"><button className="button primary" onClick={() => setModal('upload')}>Upload document <UploadCloud size={16} /></button></div></Modal>}
    {modal === 'notifications' && <Modal title="Workspace updates" close={() => setModal(null)}><div className="modal-body"><div className="notification-item"><Microscope size={22} /><div><h3>Evidence pipeline ready</h3><p>Upload a document, run recognition, then review model conflicts here.</p></div></div><div className="notification-item"><ShieldCheck size={22} /><div><h3>MongoDB GridFS active</h3><p>Uploaded originals persist in the backend with their SHA-256 evidence hash.</p></div></div></div></Modal>}
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
  onCancelFullOcr,
  parsingRun,
  vlJobState,
  onRunDocumentIntelligence,
  onCancelDocumentIntelligence,
  activeBlockId,
  setActiveBlockId,
  tab,
  setTab,
  events,
  fusionResult,
  fusionJobState,
  onRunEvidenceFusion,
  recoveringRegions,
  onRunTargetedRecovery,
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
  jobState?: { running: boolean; jobId?: string; status?: string; stage?: string; error?: string; elapsedSeconds?: number };
  onRunFullOcr: (force?: boolean) => void;
  onCancelFullOcr: () => void;
  parsingRun: DocumentParsingRunResult | null;
  vlJobState?: { running: boolean; jobId?: string; status?: string; stage?: string; error?: string; elapsedSeconds?: number };
  onRunDocumentIntelligence: (force?: boolean) => void;
  onCancelDocumentIntelligence: () => void;
  activeBlockId: string | null;
  setActiveBlockId: (id: string | null) => void;
  tab: 'Parse' | 'Extract' | 'Review' | 'Compare';
  setTab: (tab: 'Parse' | 'Extract' | 'Review' | 'Compare') => void;
  events: AuditEvent[];
  fusionResult: FusionRunDetail | null;
  fusionJobState?: { running: boolean; runId?: string; status?: string; error?: string };
  onRunEvidenceFusion: () => void;
  recoveringRegions: Record<string, boolean>;
  onRunTargetedRecovery: (regionId: string) => void;
}) {
  const [subTab, setSubTab] = useState<'layout' | 'markdown' | 'tables' | 'regions' | 'fusion'>('layout');

  const hasDetected = detectedRegions.length > 0;
  const hasParsingRun = Boolean(parsingRun && parsingRun.pages && parsingRun.pages.length > 0);
  const hasFusionRun = Boolean(fusionResult);
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



  // If Tab is Activity


  // If Tab is Parse
  if (!hasParsingRun && !vlJobState?.running) {
    return (
      <div className="welcome-actions" style={{ padding: '80px 40px', textAlign: 'center', background: '#fafcf8', borderRadius: 8, border: '1px dashed #d5ded0' }}>
        <Sparkles size={40} style={{ color: '#2b5e39', margin: '0 auto 16px' }} />
        <h2 style={{ marginBottom: 12, color: '#163321', fontSize: 22 }}>Document uploaded successfully.</h2>
        <p style={{ color: '#526958', marginBottom: 32, fontSize: 15, maxWidth: 500, marginLeft: 'auto', marginRight: 'auto' }}>
          Your original document is securely hashed and stored in MongoDB GridFS. Select your processing workflow below.
        </p>
        <div style={{ display: 'flex', gap: 24, justifyContent: 'center' }}>
          <button 
            className="button primary" 
            style={{ padding: '16px 32px', fontSize: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: 'auto', borderRadius: 12, background: '#1c4228' }} 
            onClick={() => { setTab('Parse'); onRunDocumentIntelligence(false); }}
          >
            <FileText size={28} /> 
            <div>
              <strong style={{ display: 'block', fontSize: 16 }}>Parse</strong>
              <small style={{ fontSize: 12, opacity: 0.8, fontWeight: 400 }}>Full layout & Markdown</small>
            </div>
          </button>
          <button 
            className="button primary" 
            style={{ padding: '16px 32px', fontSize: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, height: 'auto', borderRadius: 12, background: '#245340' }} 
            onClick={() => { setTab('Extract'); onRunDocumentIntelligence(false); }}
          >
            <LayoutDashboard size={28} /> 
            <div>
              <strong style={{ display: 'block', fontSize: 16 }}>Extract</strong>
              <small style={{ fontSize: 12, opacity: 0.8, fontWeight: 400 }}>Schema-driven JSON</small>
            </div>
          </button>
        </div>
      </div>
    );
  }

  if (tab === 'Parse') {
    return <ParsePanel 
      vlJobState={vlJobState}
      hasParsingRun={hasParsingRun}
      parsingRun={parsingRun}
      onCancelDocumentIntelligence={onCancelDocumentIntelligence}
      onRunDocumentIntelligence={onRunDocumentIntelligence}
      jobState={jobState}
      onRunFullOcr={onRunFullOcr}
      onCancelFullOcr={onCancelFullOcr}
      subTab={subTab}
      setSubTab={setSubTab}
      layoutBlocks={layoutBlocks}
      activeBlockId={activeBlockId}
      setActiveBlockId={setActiveBlockId}
    />;
  }

  // If Tab is Extract
  if (tab === 'Extract') {
    return <ExtractPanel hasParsingRun={hasParsingRun} parsingRun={parsingRun} vlJobState={vlJobState} />;
  }

  // If Tab is Review
  if (tab === 'Review') {
    return <ReviewPanel 
      hasParsingRun={hasParsingRun} 
      layoutBlocks={layoutBlocks} 
      doc={doc}
      corrections={corrections}
      onResolve={onResolve}
      activeBlockId={activeBlockId}
      setActiveBlockId={setActiveBlockId}
    />;
  }

  // If Tab is Compare
  if (tab === 'Compare') {
    return <ComparePanel />;
  }

  return null;
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

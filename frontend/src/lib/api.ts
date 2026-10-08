import type { DocumentItem, ReviewStatus } from './data';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

export type ApiDocumentItem = {
  id: string;
  name: string;
  kind: string;
  language: string;
  pages: number;
  status: string;
  added: string;
  size: string;
  sample: boolean;
  url?: string;
  mime?: string;
  revision: number;
  sha256?: string;
  gridfs_file_id?: string;
  file_size_bytes?: number;
};

export type DocumentUploadResult = {
  document_id: string;
  name: string;
  original_filename?: string;
  content_type?: string;
  file_size_bytes?: number;
  sha256?: string;
  gridfs_file_id?: string;
  page_count: number;
  source_url?: string;
  status: string;
  revision: number;
  created_at?: string;
};

export async function fetchDocumentsFromApi(query?: string, statusFilter?: string): Promise<DocumentItem[]> {
  const params = new URLSearchParams();
  if (query && query.trim()) params.set('search', query.trim());
  if (statusFilter && statusFilter !== 'All statuses') params.set('status', statusFilter);

  const url = `${API_BASE}/documents${params.toString() ? '?' + params.toString() : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch documents: ${res.statusText}`;
    throw new Error(message);
  }
  const data = await res.json();
  return (data.items || []).map((item: ApiDocumentItem) => ({
    id: item.id,
    name: item.name,
    kind: item.kind,
    language: item.language,
    pages: item.pages,
    status: (item.status === 'Needs review' || item.status === 'Reviewed' || item.status === 'Ready for backend')
      ? (item.status as ReviewStatus)
      : 'Ready for backend',
    added: item.added || 'Uploaded',
    size: item.size || '1.0 MB',
    sample: item.sample || false,
    url: item.url || `${API_BASE}/documents/${item.id}/file`,
    mime: item.mime || 'application/pdf',
    sha256: item.sha256,
    gridfs_file_id: item.gridfs_file_id,
  }));
}

export async function uploadDocumentToApi(
  file: File,
  title: string,
  kind: string,
  language: string
): Promise<DocumentUploadResult> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('title', title);
  formData.append('kind', kind);
  formData.append('expected_language', language);

  const res = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Upload failed (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }

  return await res.json();
}

export type RegionRecognitionResult = {
  document_id: string;
  region_id: string;
  recognized_text: string;
  confidence: number;
  execution_time_ms: number;
  model_identifier: string;
  model_version: string;
  bounding_box: { x: number; y: number; w: number; h: number };
  candidate: {
    text: string;
    confidence?: number;
    calibrated_score?: number;
    provider_id: string;
    model_version: string;
  };
  is_verified: boolean;
};

export async function recognizeRegionApi(
  documentId: string,
  regionId: string,
  boundingBox?: { x: number; y: number; w: number; h: number },
  pageIndex: number = 0
): Promise<RegionRecognitionResult> {
  const url = `${API_BASE}/documents/${documentId}/regions/${regionId}/recognize`;
  const body = boundingBox ? { bounding_box: boundingBox, page_index: pageIndex } : { page_index: pageIndex };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Recognition failed (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }

  return await res.json();
}

export type DetectedDocumentRegion = {
  id: string;
  document_id: string;
  page_index: number;
  line: string;
  original: string;
  bounding_box: { x: number; y: number; w: number; h: number };
  polygon?: number[][];
  confidence?: number;
  provider_id?: string;
  model_version?: string;
  candidates_detail?: Array<{
    text: string;
    confidence?: number;
    calibrated_score?: number;
    provider_id: string;
    model_version: string;
  }>;
  status: string;
  reviewer_decision?: string;
  is_illegible: boolean;
};

export type DocumentRegionsListResult = {
  document_id: string;
  total: number;
  items: DetectedDocumentRegion[];
};

export type JobResponseData = {
  job_id: string;
  document_id: string;
  status: string;
  stage: string;
  provider: string;
  model: string;
  created_at: string;
};

export type JobStatusDetail = {
  job_id: string;
  document_id: string;
  status: string;
  stage: string;
  provider: string;
  model: string;
  provider_job_id?: string;
  processed_page_count: number;
  execution_time_ms?: number;
  error?: string;
  retry_count: number;
  started_at?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
};

export async function scheduleDocumentRecognitionApi(
  documentId: string,
  pipelineVersion: string = 'v1.0.0'
): Promise<JobResponseData> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/recognition`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_version: pipelineVersion }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Recognition schedule failed (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }

  return await res.json();
}

export async function getJobStatusApi(jobId: string): Promise<JobStatusDetail> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch job status (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }
  return await res.json();
}

export async function fetchDocumentRegionsApi(documentId: string): Promise<DetectedDocumentRegion[]> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/regions`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch document regions (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }
  const data: DocumentRegionsListResult = await res.json();
  return data.items || [];
}

export async function fetchDocumentJobsApi(documentId: string): Promise<JobStatusDetail[]> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/jobs`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch document jobs (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }
  return await res.json();
}

export type LayoutBlockDetail = {
  block_id: string;
  page_index: number;
  block_type: string;
  bounding_box: { x: number; y: number; w: number; h: number };
  polygon?: number[][];
  raw_bbox?: number[];
  content: string;
  reading_order: number;
  confidence?: number;
};

export type ParsedPageDetail = {
  page_index: number;
  width: number;
  height: number;
  markdown_text: string;
  blocks: LayoutBlockDetail[];
  reading_order_sequence: string[];
  tables_count: number;
};

export type DocumentParsingRunResult = {
  id: string;
  document_id: string;
  job_id: string;
  provider_id: string;
  model_version: string;
  provider_job_id?: string;
  input_sha256?: string;
  page_count: number;
  markdown_text: string;
  pages: ParsedPageDetail[];
  total_blocks: number;
  execution_time_ms: number;
  created_at: string;
};

export async function scheduleDocumentIntelligenceApi(
  documentId: string,
  pipelineVersion: string = 'v1.0.0'
): Promise<JobResponseData> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/document-intelligence`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_version: pipelineVersion }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Document intelligence scheduling failed (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }

  return await res.json();
}

export async function fetchParsedDocumentApi(documentId: string): Promise<DocumentParsingRunResult | null> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/parsed-document`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch parsed document (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }
  return await res.json();
}

export async function fetchParsingHistoryApi(documentId: string): Promise<DocumentParsingRunResult[]> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/parsing-history`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const message = errorData?.error?.message || `Failed to fetch parsing history (${res.status}): ${res.statusText}`;
    throw new Error(message);
  }
  return await res.json();
}



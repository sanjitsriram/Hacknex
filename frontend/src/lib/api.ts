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

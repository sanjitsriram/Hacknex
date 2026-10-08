export type ReviewStatus = 'Needs review' | 'Reviewed' | 'Ready for backend';
export type DocumentItem = { id: string; name: string; kind: string; language: string; pages: number; status: ReviewStatus; added: string; size: string; sample: boolean; url?: string; mime?: string };
export type Region = { id: string; line: string; original: string; alternatives: string[]; reason: string; x: number; y: number; w: number; h: number };
export const samples: DocumentItem[] = [
  { id: 'demo-1', name: 'Field notes — site inspection', kind: 'Field notes', language: 'English', pages: 1, status: 'Needs review', added: 'Sample document', size: 'Illustrative source', sample: true },
  { id: 'demo-2', name: 'Archive letter — October 1948', kind: 'Correspondence', language: 'English', pages: 1, status: 'Ready for backend', added: 'Sample document', size: 'Workflow example', sample: true },
  { id: 'demo-3', name: 'Lab notebook — observation 07', kind: 'Research notes', language: 'English', pages: 1, status: 'Ready for backend', added: 'Sample document', size: 'Workflow example', sample: true },
];
export const regions: Region[] = [
  { id: 'r1', line: 'The north wall measures 4.8 metres.', original: '4.8', alternatives: ['4.8', '4.3'], reason: 'The whole-line reading and word crop disagree on the last digit.', x: 57, y: 29.8, w: 12, h: 5 },
  { id: 'r2', line: 'Follow up with Mr. Harris on Friday.', original: 'Harris', alternatives: ['Harris', 'Harvis'], reason: 'Two recognition candidates disagree on the middle letter pair.', x: 46, y: 45.5, w: 19, h: 5 },
  { id: 'r3', line: 'Replace the bracket before inspection.', original: 'bracket', alternatives: ['bracket', 'basket'], reason: 'Overlapping strokes reduce the legibility of this region.', x: 33, y: 56, w: 24, h: 5 },
];
export const baseText = 'Site inspection · 08 October 2026\n\nArrived at the east entrance at 09:15.\nThe north wall measures 4.8 metres.\nSurface is dry; no visible cracks.\n\nFollow up with Mr. Harris on Friday.\nCheck the joints along the window.\nReplace the bracket before inspection.\n\nMaterials required:\n2 timber panels, 6 bolts, primer.\n\nNext visit: 12 October, 10:30 am.';
export type AuditEvent = { id: string; time: string; action: string; detail: string };
export type Preferences = { reviewer: string; language: string; highlight: boolean; strict: boolean };
export const defaultPreferences: Preferences = { reviewer: 'Sanjit', language: 'English', highlight: true, strict: true };
export function updateRegionText(text: string, region: Region, previous: string, next: string): string | null {
  const location = region.line.indexOf(region.original);
  const prefix = region.line.slice(0, location);
  const suffix = region.line.slice(location + region.original.length);
  const expected = prefix + previous + suffix;
  const lines = text.split('\n');
  const lineIndex = lines.findIndex(line => line === expected);
  if (lineIndex < 0 || lines.lastIndexOf(expected) !== lineIndex) return null;
  lines[lineIndex] = prefix + next + suffix;
  return lines.join('\n');
}
export function parseSavedState(raw: string) {
  const data = JSON.parse(raw);
  if (!data || typeof data !== 'object' || typeof data.text !== 'string' || data.text.length > 100000 || !data.preferences || typeof data.preferences.reviewer !== 'string' || !data.preferences.reviewer.trim() || !data.corrections || typeof data.corrections !== 'object' || Array.isArray(data.corrections) || !Array.isArray(data.events)) throw new Error('Invalid saved workspace');
  const corrections: Record<string, string> = {};
  for (const region of regions) if (typeof data.corrections[region.id] === 'string' && data.corrections[region.id].trim() && data.corrections[region.id].length <= 100) corrections[region.id] = data.corrections[region.id];
  const events: AuditEvent[] = data.events.filter((event: AuditEvent) => event && typeof event.id === 'string' && typeof event.action === 'string' && typeof event.detail === 'string' && typeof event.time === 'string' && Number.isFinite(Date.parse(event.time))).slice(0, 500);
  return { text: data.text as string, corrections, events, reviewed: data.reviewed === true && regions.every(region => region.id in corrections), preferences: { ...defaultPreferences, reviewer: data.preferences.reviewer.trim().slice(0, 50), language: ['English', 'Tamil', 'Hindi', 'Mixed / unknown'].includes(data.preferences.language) ? data.preferences.language : 'English', highlight: data.preferences.highlight !== false } };
}
export function validateFile(file: Pick<File, 'type' | 'size' | 'name'>): string | null {
  if (!['image/png', 'image/jpeg', 'image/webp', 'application/pdf'].includes(file.type)) return `${file.name}: use a PNG, JPG, WebP or PDF file.`;
  if (file.size === 0) return `${file.name}: this file is empty.`;
  if (file.size > 20 * 1024 * 1024) return `${file.name}: maximum file size is 20 MB.`;
  return null;
}

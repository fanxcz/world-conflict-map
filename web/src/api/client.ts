/** Base URL of the backend API. Empty = same origin (local dev via vite proxy).
 *  For static hosting (e.g. GitHub Pages) set VITE_API_URL to the public
 *  https:// URL of your backend. No secrets here — public config only. */
export const API_BASE = (import.meta.env.VITE_API_URL as string || '').replace(/\/$/, '');

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Conflict {
  id: number;
  name: string;
  slug: string;
  region: string;
  description: string | null;
  status: string;
  start_date: string | null;
  end_date: string | null;
  last_updated: string;
  geometry: { type: string; coordinates: unknown } | null;
  geometry_type: string | null;
  is_sample: boolean;
  sources: ApiSource[];
}

export interface WcmEvent {
  id: number;
  conflict_id: number | null;
  type: string;
  title: string;
  description: string | null;
  latitude: number;
  longitude: number;
  event_time: string;
  confidence: string;
  is_sample: boolean;
  sources: ApiSource[];
}

export interface ApiSource {
  id: number;
  title: string;
  publisher: string | null;
  url: string | null;
  published_at: string | null;
  accessed_at: string | null;
  reliability_note: string | null;
}

export interface Filters {
  region: string;
  conflictId: string;
  eventType: string;
  status: string;
  confidence: string;
  dateFrom: string;
  dateTo: string;
  sourceId: string;
  search: string;
}

export const EMPTY_FILTERS: Filters = {
  region: '',
  conflictId: '',
  eventType: '',
  status: '',
  confidence: '',
  dateFrom: '',
  dateTo: '',
  sourceId: '',
  search: '',
};

export interface DataSource {
  id: number;
  name: string;
  publisher: string | null;
  url: string;
  source_type: string;
  type: string;
  enabled: boolean;
  auto_approve: boolean;
  trust_level: string;
  update_interval: string;
  status: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_success_at: string | null;
  last_update: string | null;
  last_error: string | null;
  error_count: number;
  items_received: number;
  items_approved: number;
  fetch_config: Record<string, unknown> | null;
  is_demo: boolean;
}

export interface PendingItem {
  id: number;
  source_id: number | null;
  source_name?: string | null;
  external_id: string | null;
  title: string;
  description: string | null;
  event_type: string;
  latitude: number | null;
  longitude: number | null;
  geometry: { type: string; coordinates: unknown } | null;
  location_status: string;
  event_time: string | null;
  published_at: string | null;
  confidence: string;
  source_url: string | null;
  conflict_id: number | null;
  status: string;
  duplicate_candidate: boolean;
  candidate_ids: { ids: number[]; reason: string } | null;
  approved_event_id: number | null;
  provenance: Record<string, string | null> | null;
  version: number;
}

export interface ImporterDashboard {
  sources: number;
  active: number;
  errors: number;
  pending: number;
  approved_today: number;
  rejected_today: number;
  last_update: string | null;
  public_last_updated: string | null;
}

function token(): string | null {
  return localStorage.getItem('wcm_token');
}

export function authHeaders(): Record<string, string> {
  const t = token();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const full = path.startsWith('/api') ? API_BASE + path : path;
  const res = await fetch(full, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text.slice(0, 300)}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export const api = {
  conflicts: (p: Record<string, string | number> = {}) =>
    req<Paged<Conflict>>('/api/conflicts?' + new URLSearchParams(p as Record<string, string>)),
  conflict: (id: number) => req<Conflict>(`/api/conflicts/${id}`),
  createConflict: (b: unknown) => req<Conflict>('/api/conflicts', { method: 'POST', body: JSON.stringify(b) }),
  updateConflict: (id: number, b: unknown) => req<Conflict>(`/api/conflicts/${id}`, { method: 'PUT', body: JSON.stringify(b) }),
  deleteConflict: (id: number) =>
    req<void>(`/api/conflicts/${id}`, { method: 'DELETE', headers: { ...authHeaders() } } as RequestInit),
  events: (p: Record<string, string | number> = {}) =>
    req<Paged<WcmEvent>>('/api/events?' + new URLSearchParams(p as Record<string, string>)),
  createEvent: (b: unknown) => req<WcmEvent>('/api/events', { method: 'POST', body: JSON.stringify(b) }),
  updateEvent: (id: number, b: unknown) => req<WcmEvent>(`/api/events/${id}`, { method: 'PUT', body: JSON.stringify(b) }),
  deleteEvent: (id: number) => req<void>(`/api/events/${id}`, { method: 'DELETE' }),
  sources: () => req<Paged<ApiSource>>('/api/sources?page=1&page_size=200'),
  createSource: (b: unknown) => req<ApiSource>('/api/sources', { method: 'POST', body: JSON.stringify(b) }),
  regions: () => req<{ id: number; name: string; slug: string }[]>('/api/regions'),
  countries: (search = '') => req<Paged<{ id: number; name: string; capital: string | null; lat: number | null; lon: number | null }>>(`/api/countries?search=${encodeURIComponent(search)}&page_size=50`),
  geojson: (p: Record<string, string> = {}) => req<GeoJSON.FeatureCollection>('/api/map/geojson?' + new URLSearchParams(p)),
  timeline: (date?: string) => req<{ total_events: number; by_type: Record<string, number>; by_confidence: Record<string, number>; latest: { id: number; title: string; type: string; event_time: string }[] }>(`/api/timeline${date ? `?date=${date}` : ''}`),
  login: (email: string, password: string) =>
    req<{ access_token: string }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => req<{ id: number; email: string; role: string }>('/api/auth/me'),
  audit: () => req<Paged<{ id: number; user: string; action: string; object_type: string; object_id: number | null; timestamp: string }>>('/api/audit-logs?page=1&page_size=100'),
  features: () => req<Paged<{ id: number; name: string | null; feature_type: string; layer: string; geometry: { type: string; coordinates: unknown } }>>('/api/map/features?page=1&page_size=200'),
  createFeature: (b: unknown) => req<{ id: number }>('/api/map/features', { method: 'POST', body: JSON.stringify(b) }),
  deleteFeature: (id: number) => req<void>(`/api/map/features/${id}`, { method: 'DELETE' }),
  // ---- moderated import pipeline (AUTO-PUBLISH=OFF; public map gets APPROVED only) ----
  dataSources: () => req<DataSource[]>('/api/data-sources'),
  createDataSource: (b: unknown) => req<DataSource>('/api/data-sources', { method: 'POST', body: JSON.stringify(b) }),
  updateDataSource: (id: number, b: unknown) => req<DataSource>(`/api/data-sources/${id}`, { method: 'PUT', body: JSON.stringify(b) }),
  deleteDataSource: (id: number) => req<void>(`/api/data-sources/${id}`, { method: 'DELETE' }),
  testDataSource: (id: number) => req<Record<string, unknown>>(`/api/data-sources/${id}/test`, { method: 'POST' }),
  runDataSource: (id: number) => req<{ fetched: number; new: number; duplicates: number; invalid: number; pending_review: number; status: string; error: string | null; message: string }>(`/api/data-sources/${id}/update`, { method: 'POST' }),
  enableDataSource: (id: number) => req<DataSource>(`/api/data-sources/${id}/enable`, { method: 'POST' }),
  disableDataSource: (id: number) => req<DataSource>(`/api/data-sources/${id}/disable`, { method: 'POST' }),
  pending: (p: Record<string, string | number> = {}) =>
    req<Paged<PendingItem>>('/api/pending?' + new URLSearchParams(p as Record<string, string>)),
  imports: (p: Record<string, string | number> = {}) =>
    req<Paged<PendingItem>>('/api/imports?' + new URLSearchParams(p as Record<string, string>)),
  importDetail: (id: number) => req<PendingItem & { raw_meta?: { id: number; fetched_at: string; hash: string } | null }>(`/api/imports/${id}`),
  editPending: (id: number, b: unknown) => req<PendingItem>(`/api/pending/${id}`, { method: 'PUT', body: JSON.stringify(b) }),
  approvePending: (id: number, b: unknown = {}) => req<{ event_id: number; title: string }>(`/api/pending/${id}/approve`, { method: 'POST', body: JSON.stringify(b) }),
  rejectPending: (id: number, reason = '') => req<PendingItem>(`/api/pending/${id}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),
  duplicatePending: (id: number, of_id: number, kind = 'event') => req<PendingItem>(`/api/pending/${id}/duplicate`, { method: 'POST', body: JSON.stringify({ of_id, kind }) }),
  mergePending: (id: number, into_event_id: number) => req<{ event_id: number }>(`/api/pending/${id}/merge`, { method: 'POST', body: JSON.stringify({ into_event_id }) }),
  pendingHistory: (id: number) => req<{ version: number; who: string; timestamp: string | null; changes: unknown }[]>(`/api/pending/${id}/history`),
  importLogs: (p: Record<string, string | number> = {}) =>
    req<Paged<{ id: number; source_id: number; started_at: string; finished_at: string | null; status: string; fetched: number; new: number; duplicates: number; invalid: number; error: string | null }>>('/api/import-logs?' + new URLSearchParams(p as Record<string, string>)),
  importerDashboard: () => req<ImporterDashboard>('/api/importer/dashboard'),
  freshness: () => req<{ last_updated: string | null; stale: boolean; note: string }>('/api/freshness'),
};

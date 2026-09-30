import { useQuery } from '@tanstack/react-query';
import { api, type Filters, EMPTY_FILTERS } from '../api/client';

export const EVENT_TYPES = ['clash', 'airstrike', 'artillery', 'explosion', 'infrastructure_damage', 'territorial_change', 'military_movement', 'ceasefire', 'diplomatic', 'humanitarian'];
export const LAYERS = ['countries', 'borders', 'capitals', 'cities', 'roads', 'rivers', 'conflict_zones', 'frontlines', 'incidents', 'movements', 'important'];

export function FilterPanel({ filters, setFilters, visibleLayers, setVisibleLayers }: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  visibleLayers: Record<string, boolean>;
  setVisibleLayers: (v: Record<string, boolean>) => void;
}) {
  const conflicts = useQuery({ queryKey: ['conflicts-all'], queryFn: () => api.conflicts({ page: 1, page_size: 200 }) });
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.sources() });
  const set = (k: keyof Filters, v: string) => setFilters({ ...filters, [k]: v });
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>Filters</strong>
        <button onClick={() => setFilters({ ...EMPTY_FILTERS })}>RESET FILTERS</button>
      </div>
      <label>Region</label>
      <select value={filters.region} onChange={(e) => set('region', e.target.value)}>
        <option value="">All</option>
        {['Europe', 'Middle East', 'Africa', 'Asia', 'Americas', 'Other'].map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <label>Conflict</label>
      <select value={filters.conflictId} onChange={(e) => set('conflictId', e.target.value)}>
        <option value="">All</option>
        {(conflicts.data?.items || []).map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
      </select>
      <label>Event type</label>
      <select value={filters.eventType} onChange={(e) => set('eventType', e.target.value)}>
        <option value="">All</option>
        {EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <label>Status</label>
      <select value={filters.status} onChange={(e) => set('status', e.target.value)}>
        <option value="">All</option>
        <option value="active">active</option>
        <option value="historical">historical</option>
        <option value="reported">reported</option>
      </select>
      <label>Confidence</label>
      <select value={filters.confidence} onChange={(e) => set('confidence', e.target.value)}>
        <option value="">All</option>
        <option value="CONFIRMED">CONFIRMED</option>
        <option value="REPORTED">REPORTED</option>
        <option value="UNVERIFIED">UNVERIFIED</option>
      </select>
      <label>Date from</label>
      <input type="date" value={filters.dateFrom} onChange={(e) => set('dateFrom', e.target.value)} />
      <label>Date to</label>
      <input type="date" value={filters.dateTo} onChange={(e) => set('dateTo', e.target.value)} />
      <label>Source</label>
      <select value={filters.sourceId} onChange={(e) => set('sourceId', e.target.value)}>
        <option value="">All</option>
        {(sources.data?.items || []).map((s) => <option key={s.id} value={String(s.id)}>{s.title}</option>)}
      </select>
      <div style={{ marginTop: 12 }}>
        <strong>Layers</strong>
        {LAYERS.map((l) => (
          <div key={l}>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" style={{ width: 14 }} checked={visibleLayers[l] !== false}
                onChange={(e) => setVisibleLayers({ ...visibleLayers, [l]: e.target.checked })} />
              {l.replace('_', ' ')}
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}

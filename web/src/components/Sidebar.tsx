import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function Sidebar({ tab, setTab, region, setRegion, onOpenConflict }: {
  tab: string; setTab: (t: string) => void;
  region: string; setRegion: (r: string) => void;
  onOpenConflict: (id: number) => void;
}) {
  const q = useQuery({
    queryKey: ['side-conf', tab, region],
    queryFn: () => api.conflicts({
      page: 1, page_size: 50,
      ...(tab !== 'all' ? { status: tab } : {}),
      ...(region && region !== 'All' ? { region } : {}),
    }),
  });
  return (
    <div>
      <h3 style={{ margin: '4px 0' }}>CONFLICTS</h3>
      {['active', 'historical', 'reported'].map((t) => (
        <button key={t} onClick={() => setTab(t === tab ? 'all' : t)}
          className={tab === t ? 'primary' : ''} style={{ marginRight: 4, marginBottom: 4 }}>
          {t[0].toUpperCase() + t.slice(1)}
        </button>
      ))}
      <h3 style={{ margin: '8px 0 4px' }}>REGIONS</h3>
      {['All', 'Europe', 'Middle East', 'Africa', 'Asia', 'Americas', 'Other'].map((r) => (
        <div key={r}>
          <button onClick={() => setRegion(r === 'All' ? '' : r)}
            className={(region || 'All') === r || (r === 'All' && !region) ? 'primary' : ''}
            style={{ width: '100%', textAlign: 'left', marginBottom: 2 }}>{r}</button>
        </div>
      ))}
      <div style={{ marginTop: 8 }}>
        {(q.data?.items || []).map((c) => (
          <div key={c.id} className="card" style={{ cursor: 'pointer' }} onClick={() => onOpenConflict(c.id)}>
            <div><strong>{c.name}</strong> {c.is_sample && <span className="badge">SAMPLE</span>}</div>
            <div><span className={`badge ${c.status}`}>{c.status.toUpperCase()}</span> <span style={{ color: '#9aa6b8' }}>{c.region}</span></div>
          </div>
        ))}
        {q.isLoading && <div>Loading…</div>}
        {q.data && q.data.items.length === 0 && <div style={{ color: '#9aa6b8' }}>No conflicts.</div>}
      </div>
    </div>
  );
}

export function ConflictCard({ id, onClose, onFly }: { id: number; onClose: () => void; onFly: (lon: number, lat: number) => void }) {
  const c = useQuery({ queryKey: ['conf', id], queryFn: () => api.conflict(id) });
  const ev = useQuery({ queryKey: ['conf-ev', id], queryFn: () => api.events({ conflict_id: id, page_size: 50 }) });
  if (c.isLoading) return <div className="detail">Loading…</div>;
  if (c.error || !c.data) return <div className="detail">Not found <button onClick={onClose}>Close</button></div>;
  const d = c.data;
  return (
    <div className="detail">
      <div className="sitrep-meta">SITREP // CONFLICT #{d.id}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <strong>{d.name}</strong>
        <button onClick={onClose}>✕</button>
      </div>
      <div className="sitrep-meta" style={{ marginTop: 6 }}>
        <div>STATUS <span className={`badge ${d.status}`}>{d.status.toUpperCase()}</span></div>
        <div>REGION {d.region} · SINCE {d.start_date || '—'}</div>
        <div>UPDATED {new Date(d.last_updated).toLocaleString()}</div>
        {d.is_sample && <div><span className="badge">DEMO / SAMPLE DATA</span></div>}
      </div>
      <p style={{ color: '#c6cfdb' }}>{d.description}</p>
      <h4>EVENTS ({ev.data?.total || 0})</h4>
      {(ev.data?.items || []).map((e) => (
        <div key={e.id} className="card" style={{ cursor: 'pointer' }}
          onClick={() => onFly(e.longitude, e.latitude)}>
          <div><strong>{e.title}</strong></div>
          <div style={{ fontSize: 12, color: '#9aa6b8' }}>{e.type} · {e.confidence} · {new Date(e.event_time).toLocaleDateString()}</div>
          <div style={{ fontSize: 12 }}>{e.description}</div>
        </div>
      ))}
      <h4>SOURCES</h4>
      {(d.sources || []).map((s) => (
        <div key={s.id} style={{ fontSize: 12, marginBottom: 4 }}>
          • {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}
          <span style={{ color: '#9aa6b8' }}> · {s.publisher || 'Open source'}{s.published_at ? ` · ${new Date(s.published_at).toLocaleDateString()}` : ''}</span>
        </div>
      ))}
      {(d.sources || []).length === 0 && <div style={{ fontSize: 12, color: '#9aa6b8' }}>No linked sources.</div>}
    </div>
  );
}

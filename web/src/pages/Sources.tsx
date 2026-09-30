import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

const TYPES = ['rss', 'atom', 'json_api', 'geojson', 'csv', 'xml'];
const INTERVALS = ['manual', '5m', '15m', '30m', '1h', '6h', 'daily'];
const TRUST = ['UNKNOWN', 'LOW', 'MEDIUM', 'HIGH'];

export default function Sources() {
  const qc = useQueryClient();
  const dash = useQuery({ queryKey: ['dash'], queryFn: () => api.importerDashboard() });
  const list = useQuery({ queryKey: ['dsrc'], queryFn: () => api.dataSources() });
  const [form, setForm] = useState({ name: '', url: '', source_type: 'rss', update_interval: 'manual', trust_level: 'UNKNOWN', auto_approve: false, mapping: '' });
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState<number | null>(null);

  async function wrap(id: number, fn: (n: number) => Promise<unknown>, label: string) {
    setBusy(id);
    setMsg('');
    try {
      const r = await fn(id);
      setMsg(`${label}: ` + JSON.stringify(r).slice(0, 400));
      qc.invalidateQueries();
    } catch (e) {
      setMsg(`${label} failed: ` + (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="admin">
      <Link to="/admin">← Admin</Link> <Link to="/admin/imports" style={{ marginLeft: 12 }}>Moderation queue →</Link>
      <h2>DATA SOURCES</h2>
      {dash.data && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <div className="card">Sources: {dash.data.sources}</div>
          <div className="card">Active: {dash.data.active}</div>
          <div className="card">Errors: {dash.data.errors}</div>
          <div className="card">Pending: {dash.data.pending}</div>
          <div className="card">Approved today: {dash.data.approved_today}</div>
          <div className="card">Rejected today: {dash.data.rejected_today}</div>
          <div className="card">Last update: {dash.data.last_update || '—'}</div>
        </div>
      )}
      <table>
        <thead><tr><th>Source</th><th>Type</th><th>Status</th><th>Last Update</th><th>Recv/Appr</th><th>Actions</th></tr></thead>
        <tbody>
          {(list.data || []).map((s) => (
            <tr key={s.id}>
              <td>{s.name}{s.is_demo && ' (DEMO SOURCE)'}<br /><span style={{ color: '#9aa6b8', fontSize: 12 }}>{s.url}</span>
                {s.last_error && <div style={{ color: '#ff5252', fontSize: 12 }}>Err: {s.last_error.slice(0, 120)}</div>}</td>
              <td>{s.source_type}</td>
              <td>{s.enabled ? s.status : 'DISABLED'}</td>
              <td>{s.last_update ? new Date(s.last_update).toLocaleString() : '—'}</td>
              <td>{s.items_received}/{s.items_approved}</td>
              <td>
                <button disabled={busy === s.id} onClick={() => wrap(s.id, api.testDataSource, 'TEST')}>TEST</button>{' '}
                <button disabled={busy === s.id} onClick={() => wrap(s.id, api.runDataSource, 'UPDATE NOW')}>UPDATE NOW</button>{' '}
                {s.enabled
                  ? <button onClick={() => wrap(s.id, api.disableDataSource, 'DISABLE')}>DISABLE</button>
                  : <button onClick={() => wrap(s.id, api.enableDataSource, 'ENABLE')}>ENABLE</button>}{' '}
                <button onClick={() => wrap(s.id, (n) => api.updateDataSource(n, { auto_approve: !s.auto_approve }), 'AUTO-APPROVE toggle')}>
                  AUTO:{s.auto_approve ? 'ON' : 'OFF'}</button>{' '}
                <button className="danger" onClick={async () => { if (confirm('Delete source?')) { await api.deleteDataSource(s.id); qc.invalidateQueries(); } }}>DEL</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {msg && <div className="card" style={{ whiteSpace: 'pre-wrap' }}>{msg}</div>}
      <h3>[+ ADD SOURCE]</h3>
      <div className="card" style={{ maxWidth: 560 }}>
        <label>Name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <label>URL (http/https, or local: path for DEMO)</label>
        <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://example.com/feed.xml" />
        <label>Type</label>
        <select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label>Update interval</label>
        <select value={form.update_interval} onChange={(e) => setForm({ ...form, update_interval: e.target.value })}>
          {INTERVALS.map((t) => <option key={t} value={t}>{t === 'manual' ? 'Manual' : `Every ${t}`}</option>)}
        </select>
        <label>Trust level (never auto-confirms a single event)</label>
        <select value={form.trust_level} onChange={(e) => setForm({ ...form, trust_level: e.target.value })}>
          {TRUST.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label>JSON mapping (optional, e.g. latitude→lat, longitude→lon, title→headline)</label>
        <input value={form.mapping} onChange={(e) => setForm({ ...form, mapping: e.target.value })} placeholder='{}' />
        <label style={{ display: 'flex', gap: 6 }}><input type="checkbox" style={{ width: 16 }} checked={form.auto_approve} onChange={(e) => setForm({ ...form, auto_approve: e.target.checked })} /> Auto approve (per-source, only for feeds you trust)</label>
        <div style={{ marginTop: 8 }}>
          <button className="primary" onClick={async () => {
            let mapping: Record<string, string> = {};
            try { mapping = form.mapping ? JSON.parse(form.mapping) : {}; } catch { setMsg('Bad mapping JSON'); return; }
            await api.createDataSource({ name: form.name, url: form.url, source_type: form.source_type, update_interval: form.update_interval, trust_level: form.trust_level, auto_approve: form.auto_approve, fetch_config: { mapping } });
            setForm({ name: '', url: '', source_type: 'rss', update_interval: 'manual', trust_level: 'UNKNOWN', auto_approve: false, mapping: '' });
            qc.invalidateQueries();
          }}>Add source</button>
        </div>
        <p style={{ color: '#9aa6b8', fontSize: 12 }}>Secrets (headers/auth) are masked after save. Fetches use 15s timeout, 5MB cap, 5-redirect limit; JS from feeds is never executed.</p>
      </div>
    </div>
  );
}

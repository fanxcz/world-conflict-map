import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, type PendingItem } from '../api/client';

function Card({ p, onDone }: { p: PendingItem; onDone: () => void }) {
  const [edit, setEdit] = useState(false);
  const [title, setTitle] = useState(p.title);
  const [lat, setLat] = useState(p.latitude?.toString() || '');
  const [lon, setLon] = useState(p.longitude?.toString() || '');
  const [conflictId, setConflictId] = useState(p.conflict_id?.toString() || '');
  const [msg, setMsg] = useState('');
  const conflicts = useQuery({ queryKey: ['all-conf'], queryFn: () => api.conflicts({ page_size: 200 }) });

  async function call<T>(fn: () => Promise<T>, ok: string) {
    setMsg('');
    try {
      await fn();
      setMsg(ok);
      onDone();
    } catch (e) {
      setMsg('Failed: ' + (e as Error).message);
    }
  }

  return (
    <div className="card">
      <div><strong>{p.title}</strong> {p.duplicate_candidate && <span className="badge reported">DUPLICATE CANDIDATE</span>} {p.location_status === 'LOCATION_UNKNOWN' && <span className="badge">LOCATION_UNKNOWN</span>}</div>
      <div style={{ fontSize: 12, color: '#9aa6b8' }}>
        Source: {p.source_name || `#${p.source_id}`} · Published: {p.published_at ? new Date(p.published_at).toLocaleString() : '—'}
      </div>
      <div style={{ fontSize: 13 }}>{p.description}</div>
      <div style={{ fontSize: 12 }}>Coordinates: {p.latitude ?? '—'}, {p.longitude ?? '—'} · Confidence: {p.confidence} · Type: {p.event_type}</div>
      {p.candidate_ids && <div style={{ fontSize: 12, color: '#ffb300' }}>Similar to: {JSON.stringify(p.candidate_ids)}</div>}
      {p.provenance && (
        <div style={{ fontSize: 12, color: '#9aa6b8' }}>
          Provenance: fetched {p.provenance.fetched || '—'} · published {p.provenance.published || '—'} · imported {p.provenance.imported || '—'}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        {p.source_url && <a href={p.source_url} target="_blank" rel="noreferrer"><button>VIEW SOURCE</button></a>}
        <button onClick={() => setEdit(!edit)}>EDIT</button>
        <button className="primary" onClick={() => call(
          () => api.approvePending(p.id, { conflict_id: conflictId ? Number(conflictId) : (p.conflict_id ?? null) }),
          'Approved → public map')}>
          APPROVE</button>
        <button onClick={() => call(() => api.rejectPending(p.id, 'manual review'), 'Rejected')}>REJECT</button>
        <button onClick={() => {
          const of = prompt('Mark as duplicate of EVENT id:');
          if (of) call(() => api.duplicatePending(p.id, Number(of)), 'Marked duplicate');
        }}>MARK AS DUPLICATE</button>
        <button onClick={() => {
          const into = prompt('Merge into EVENT id:');
          if (into) call(() => api.mergePending(p.id, Number(into)), 'Merged');
        }}>MERGE</button>
      </div>
      {edit && (
        <div style={{ marginTop: 6 }}>
          <label>Title</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
          <label>Latitude / Longitude (required before APPROVE when LOCATION_UNKNOWN)</label>
          <div style={{ display: 'flex', gap: 6 }}>
            <input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="50.45" />
            <input value={lon} onChange={(e) => setLon(e.target.value)} placeholder="30.52" />
          </div>
          <label>Conflict (optional link)</label>
          <select value={conflictId} onChange={(e) => setConflictId(e.target.value)}>
            <option value="">— none —</option>
            {(conflicts.data?.items || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <div style={{ marginTop: 6 }}>
            <button className="primary" onClick={() => call(
              () => api.editPending(p.id, {
                title,
                ...(lat && lon ? { latitude: Number(lat), longitude: Number(lon) } : {}),
                ...(conflictId ? { conflict_id: Number(conflictId) } : {}),
              }), 'Saved')}>Save edits</button>
          </div>
        </div>
      )}
      {msg && <div style={{ fontSize: 12, marginTop: 4 }}>{msg}</div>}
    </div>
  );
}

export default function Imports() {
  const qc = useQueryClient();
  const [status, setStatus] = useState('PENDING');
  const list = useQuery({ queryKey: ['imports', status], queryFn: () => api.imports({ status, page_size: 50 }) });
  const logs = useQuery({ queryKey: ['ilogs'], queryFn: () => api.importLogs({ page_size: 20 }) });
  const done = () => qc.invalidateQueries();

  return (
    <div className="admin">
      <Link to="/admin">← Admin</Link> <Link to="/admin/sources" style={{ marginLeft: 12 }}>Data sources →</Link>
      <h2>MODERATION QUEUE ({status})</h2>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        {['PENDING', 'APPROVED', 'REJECTED', 'DUPLICATE', 'MERGED'].map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={status === s ? 'primary' : ''}>{s}</button>
        ))}
        <span style={{ alignSelf: 'center', color: '#9aa6b8' }}>Total: {list.data?.total ?? '…'}</span>
      </div>
      {(list.data?.items || []).map((p) => <Card key={p.id} p={p} onDone={done} />)}
      <h3>IMPORT LOGS</h3>
      <table>
        <thead><tr><th>Source</th><th>Started</th><th>Status</th><th>Fetched/New/Dup/Invalid</th><th>Error</th></tr></thead>
        <tbody>
          {(logs.data?.items || []).map((l) => (
            <tr key={l.id}>
              <td>#{l.source_id}</td>
              <td>{new Date(l.started_at).toLocaleString()}</td>
              <td>{l.status}</td>
              <td>{l.fetched}/{l.new}/{l.duplicates}/{l.invalid}</td>
              <td style={{ fontSize: 12 }}>{l.error?.slice(0, 120) || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

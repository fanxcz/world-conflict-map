import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import MapEditor from '../components/MapEditor';
import { Link } from 'react-router-dom';

export default function Admin() {
  const [email, setEmail] = useState('admin@wcm.local');
  const [password, setPassword] = useState('');
  const [me, setMe] = useState<{ email: string; role: string } | null>(null);
  const [err, setErr] = useState('');
  const qc = useQueryClient();
  const conflicts = useQuery({ queryKey: ['adm-conf'], queryFn: () => api.conflicts({ page_size: 100 }), enabled: !!me });
  const events = useQuery({ queryKey: ['adm-ev'], queryFn: () => api.events({ page_size: 100 }), enabled: !!me });
  const audit = useQuery({ queryKey: ['adm-audit'], queryFn: () => api.audit(), enabled: !!me });
  const [cName, setCName] = useState('');
  const [cRegion, setCRegion] = useState('Europe');
  const [eTitle, setETitle] = useState('');
  const [eLat, setELat] = useState('50.0');
  const [eLon, setELon] = useState('30.0');

  async function login() {
    setErr('');
    try {
      const t = await api.login(email, password);
      localStorage.setItem('wcm_token', t.access_token);
      const m = await api.me();
      setMe(m);
      qc.invalidateQueries();
    } catch (e) {
      setErr('Login failed: ' + (e as Error).message);
    }
  }

  return (
    <div className="admin">
      <Link to="/">← Back to map</Link>
      <span style={{ marginLeft: 12 }}><Link to="/admin/sources">Data sources</Link></span>
      <span style={{ marginLeft: 12 }}><Link to="/admin/imports">Moderation queue</Link></span>
      <h2>Admin panel</h2>
      {!me ? (
        <div className="card" style={{ maxWidth: 380 }}>
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} />
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <div style={{ marginTop: 8 }}><button className="primary" onClick={login}>Login</button></div>
          {err && <div style={{ color: '#ff5252' }}>{err}</div>}
          <p style={{ color: '#9aa6b8' }}>Default seed: admin@wcm.local / Admin123! (change via .env)</p>
        </div>
      ) : (
        <div>
          <div>Logged in as <strong>{me.email}</strong> ({me.role}) <button onClick={() => { localStorage.removeItem('wcm_token'); setMe(null); }}>Logout</button></div>
          <h3>Dashboard</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <div className="card">Conflicts: {conflicts.data?.total ?? '…'}</div>
            <div className="card">Events: {events.data?.total ?? '…'}</div>
            <div className="card">Audit: {audit.data?.total ?? '…'}</div>
          </div>
          <h3>Create conflict</h3>
          <div className="card" style={{ maxWidth: 480 }}>
            <label>Name</label>
            <input value={cName} onChange={(e) => setCName(e.target.value)} />
            <label>Region</label>
            <select value={cRegion} onChange={(e) => setCRegion(e.target.value)}>
              {['Europe', 'Middle East', 'Africa', 'Asia', 'Americas', 'Other'].map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <div style={{ marginTop: 8 }}>
              <button className="primary" onClick={async () => {
                await api.createConflict({ name: cName, region: cRegion, status: 'active' });
                setCName(''); qc.invalidateQueries();
              }}>Create</button>
            </div>
          </div>
          <h3>Conflicts</h3>
          <table>
            <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {(conflicts.data?.items || []).map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td><td>{c.name}</td><td>{c.status}</td>
                  <td>
                    <button onClick={async () => { await api.updateConflict(c.id, { status: c.status === 'active' ? 'historical' : 'active' }); qc.invalidateQueries(); }}>Toggle status</button>{' '}
                    <button className="danger" onClick={async () => { if (confirm('Delete?')) { await api.deleteConflict(c.id); qc.invalidateQueries(); } }}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Create event</h3>
          <div className="card" style={{ maxWidth: 480 }}>
            <label>Title</label>
            <input value={eTitle} onChange={(e) => setETitle(e.target.value)} />
            <label>Lat</label><input value={eLat} onChange={(e) => setELat(e.target.value)} />
            <label>Lon</label><input value={eLon} onChange={(e) => setELon(e.target.value)} />
            <div style={{ marginTop: 8 }}>
              <button className="primary" onClick={async () => {
                await api.createEvent({ type: 'clash', title: eTitle || 'New event', latitude: Number(eLat), longitude: Number(eLon), event_time: new Date().toISOString(), confidence: 'REPORTED' });
                setETitle(''); qc.invalidateQueries();
              }}>Create</button>
            </div>
          </div>
          <h3>Events</h3>
          <table>
            <thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Actions</th></tr></thead>
            <tbody>
              {(events.data?.items || []).map((e) => (
                <tr key={e.id}>
                  <td>{e.id}</td><td>{e.title}</td><td>{e.type}</td>
                  <td><button className="danger" onClick={async () => { if (confirm('Delete?')) { await api.deleteEvent(e.id); qc.invalidateQueries(); } }}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Visual map editor (GeoJSON)</h3>
          <MapEditor />
          <h3>Change log</h3>
          <table>
            <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Object</th></tr></thead>
            <tbody>
              {(audit.data?.items || []).map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.timestamp).toLocaleString()}</td>
                  <td>{a.user}</td>
                  <td>{a.action} {a.object_type} #{a.object_id}</td>
                  <td>{a.object_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

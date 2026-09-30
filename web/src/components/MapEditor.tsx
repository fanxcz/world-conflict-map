import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import maplibregl from 'maplibre-gl';
import { api } from '../api/client';

type Mode = 'point' | 'line' | 'polygon';

export default function MapEditor() {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mode, setMode] = useState<Mode>('point');
  const [pts, setPts] = useState<[number, number][]>([]);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [color, setColor] = useState('#ff5252');
  const [ftype, setFtype] = useState('conflict_zone');
  const [layer, setLayer] = useState('conflict_zones');
  const [msg, setMsg] = useState('');
  const qc = useQueryClient();
  const existing = useQuery({ queryKey: ['edit-features'], queryFn: () => api.features() });
  const ptsRef = useRef<[number, number][]>([]);
  ptsRef.current = pts;

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      center: [20, 30], zoom: 2,
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    mapRef.current = map;
    map.on('click', (e) => {
      const ll: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      const m = modeRef.current;
      if (m === 'point') {
        setPts([ll]);
        draw([ll], 'Point');
      } else {
        const next = [...ptsRef.current, ll];
        setPts(next);
        draw(next, m === 'line' ? 'LineString' : 'Polygon');
      }
    });
    map.on('load', () => {
      map.addSource('edit', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'edit-fill', type: 'fill', source: 'edit', paint: { 'fill-color': '#4da3ff', 'fill-opacity': 0.3 } });
      map.addLayer({ id: 'edit-line', type: 'line', source: 'edit', paint: { 'line-color': '#4da3ff', 'line-width': 2 } });
      map.addLayer({ id: 'edit-pt', type: 'circle', source: 'edit', paint: { 'circle-color': '#4da3ff', 'circle-radius': 6 } });
    });
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  const modeRef = useRef(mode);
  modeRef.current = mode;

  function draw(coordinates: [number, number][], kind: string) {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !map.getSource('edit')) return;
    const src = map.getSource('edit') as maplibregl.GeoJSONSource;
    if (coordinates.length === 0) {
      src.setData({ type: 'FeatureCollection', features: [] } as never);
      return;
    }
    let geom: GeoJSON.Geometry;
    if (kind === 'Point') geom = { type: 'Point', coordinates: coordinates[0] };
    else if (kind === 'LineString') geom = { type: 'LineString', coordinates };
    else {
      const ring = [...coordinates];
      if (ring.length > 2) ring.push(ring[0]);
      geom = { type: 'Polygon', coordinates: [ring] };
    }
    (map.getSource('edit') as maplibregl.GeoJSONSource).setData({ type: 'Feature', geometry: geom, properties: {} } as never);
  }

  async function save() {
    setMsg('');
    if (pts.length === 0) { setMsg('Click on the map first.'); return; }
    let geom: Record<string, unknown>;
    if (mode === 'point') geom = { type: 'Point', coordinates: pts[0] };
    else if (mode === 'line') {
      if (pts.length < 2) { setMsg('Line needs ≥2 points.'); return; }
      geom = { type: 'LineString', coordinates: pts };
    } else {
      if (pts.length < 3) { setMsg('Polygon needs ≥3 points.'); return; }
      geom = { type: 'Polygon', coordinates: [[...pts, pts[0]]] };
    }
    try {
      await api.createFeature({ name: name || null, description: desc || null, feature_type: ftype, layer, color, geometry: geom, properties: {} });
      setMsg('Saved — object is now on the public map.');
      setPts([]); setName(''); setDesc('');
      qc.invalidateQueries({ queryKey: ['edit-features'] });
    } catch (e) {
      setMsg('Save failed: ' + (e as Error).message);
    }
  }

  function undo() {
    const next = pts.slice(0, -1);
    setPts(next);
    if (next.length === 0) draw([], 'Point');
    else draw(next, mode === 'line' ? 'LineString' : mode === 'polygon' ? 'Polygon' : 'Point');
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
        {(['point', 'line', 'polygon'] as Mode[]).map((m) => (
          <button key={m} onClick={() => { setMode(m); setPts([]); }} className={mode === m ? 'primary' : ''}>{m}</button>
        ))}
        <button onClick={() => { setPts([]); draw([], 'Point'); }}>Clear</button>
        <button onClick={undo} disabled={pts.length === 0}>Undo point</button>
        <button className="primary" onClick={save}>Save</button>
        <span style={{ color: '#9aa6b8' }}>{pts.length} point(s)</span>
      </div>
      <div ref={ref} style={{ height: 320, borderRadius: 8, overflow: 'hidden' }} />
      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Feature name" />
      <label>Description</label>
      <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description" />
      <label>Object type</label>
      <select value={ftype} onChange={(e) => setFtype(e.target.value)}>
        <option value="conflict_zone">conflict zone</option>
        <option value="frontline">frontline / boundary</option>
        <option value="incident">incident</option>
        <option value="movement">movement arrow</option>
        <option value="important_location">important location</option>
      </select>
      <label>Layer color</label>
      <input type="color" value={color} onChange={(e) => setColor(e.target.value)} style={{ height: 36 }} />
      <label>Layer</label>
      <select value={layer} onChange={(e) => setLayer(e.target.value)}>
        <option value="conflict_zones">conflict_zones</option>
        <option value="frontlines">frontlines</option>
        <option value="movements">movements</option>
        <option value="important">important</option>
      </select>
      {msg && <div style={{ marginTop: 8 }}>{msg}</div>}
      <p style={{ color: '#9aa6b8', fontSize: 12 }}>Click on the map to place points. For lines/polygons click several times, then Save. Use Clear to restart.</p>
      <h4>Drawn objects ({existing.data?.total ?? '…'})</h4>
      {(existing.data?.items || []).map((f) => (
        <div key={f.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 6, fontSize: 12, marginBottom: 4 }}>
          <span>#{f.id} {f.name || f.feature_type} <span style={{ color: '#9aa6b8' }}>{f.layer}</span></span>
          <button className="danger" onClick={async () => {
            if (!confirm('Delete object?')) return;
            await api.deleteFeature(f.id);
            qc.invalidateQueries({ queryKey: ['edit-features'] });
          }}>Delete</button>
        </div>
      ))}
    </div>
  );
}

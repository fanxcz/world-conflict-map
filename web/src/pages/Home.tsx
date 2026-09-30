import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import MapView from '../components/MapView';
import SearchBar from '../components/SearchBar';
import Timeline from '../components/Timeline';
import { FilterPanel } from '../components/Filters';
import { Sidebar, ConflictCard } from '../components/Sidebar';
import { EMPTY_FILTERS, API_BASE, api, type Filters } from '../api/client';
import { Link } from 'react-router-dom';

export default function Home() {
  const [filters, setFilters] = useState<Filters>({ ...EMPTY_FILTERS });
  const [tab, setTab] = useState('all');
  const [region, setRegion] = useState('');
  const [timelineDate, setTimelineDate] = useState('2026-09-30');
  const [openConflict, setOpenConflict] = useState<number | null>(null);
  const [openEvent, setOpenEvent] = useState<number | null>(null);
  const [flyTo, setFlyTo] = useState<{ lon: number; lat: number; zoom?: number; key: number } | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Record<string, boolean>>({});
  const [showFilters, setShowFilters] = useState(false);

  const merged: Filters = useMemo(() => ({
    ...filters,
    status: filters.status || (tab !== 'all' ? tab : ''),
    region: filters.region || region,
  }), [filters, tab, region]);

  const fresh = useQuery({ queryKey: ['freshness'], queryFn: () => api.freshness(), refetchInterval: 60000 });
  const eventDetail = useQuery({
    queryKey: ['event-one', openEvent],
    queryFn: () => api.events({ search: '', page_size: 1 }),
    enabled: false,
  });
  void eventDetail;

  const [eventCard, setEventCard] = useState<{ title: string; type: string } | null>(null);

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">WCM<small>SITREP // LIVE MAP</small></div>
        <SearchBar onFly={(lon, lat, zoom) => setFlyTo({ lon, lat, zoom, key: Date.now() })} />
        <button onClick={() => setShowFilters(!showFilters)}>Filters</button>
        <span style={{ fontSize: 12, color: '#9aa6b8' }} title={fresh.data?.note || ''}>
          Last updated: {fresh.data?.last_updated ? new Date(fresh.data.last_updated).toLocaleString() : '—'}
          {fresh.data?.stale && <span className="badge reported" style={{ marginLeft: 6 }}>STALE</span>}
        </span>
        <span style={{ flex: 1 }} />
        <Link to="/admin"><button>Settings / Admin</button></Link>
      </div>
      <div className="main">
        <div className="sidebar">
          {showFilters && (
            <div className="card">
              <FilterPanel filters={filters} setFilters={setFilters} visibleLayers={visibleLayers} setVisibleLayers={setVisibleLayers} />
            </div>
          )}
          <Sidebar tab={tab} setTab={setTab} region={region} setRegion={setRegion} onOpenConflict={setOpenConflict} />
        </div>
        <div className="mapwrap">
          <MapView
            filters={merged}
            timelineDate={timelineDate}
            onSelectConflict={(id) => { setOpenConflict(id); setOpenEvent(null); }}
            onSelectEvent={(id) => { setOpenEvent(id); fetchEvent(id); }}
            flyTo={flyTo}
            visibleLayers={visibleLayers}
          />
          <div className="mapbtns">
            <button onClick={() => setFlyTo({ lon: 20, lat: 30, zoom: 1.6, key: Date.now() })}>Reset view</button>
          </div>
          <div className="layerbox">
            <strong>Layers</strong>
            {['conflict_zones', 'frontlines', 'incidents', 'movements'].map((l) => (
              <label key={l} style={{ display: 'flex', gap: 6 }}>
                <input type="checkbox" style={{ width: 14 }} checked={visibleLayers[l] !== false}
                  onChange={(e) => setVisibleLayers({ ...visibleLayers, [l]: e.target.checked })} />{l}
              </label>
            ))}
          </div>
          <div className="legend">
            <strong>LEGEND</strong>
            <div className="row"><span className="sw zone" /> conflict zone</div>
            <div className="row"><span className="sw front" /> frontline / boundary</div>
            <div className="row"><span className="sw move" /> movement</div>
            <div className="row"><span className="sw inc-conf" /> incident · confirmed</div>
            <div className="row"><span className="sw inc-rep" /> incident · reported</div>
            <div className="row"><span className="sw inc-unv" /> incident · unverified</div>
          </div>
          {openConflict && (
            <ConflictCard id={openConflict} onClose={() => setOpenConflict(null)}
              onFly={(lon, lat) => setFlyTo({ lon, lat, zoom: 8, key: Date.now() })} />
          )}
          {openEvent && (
            <div className="detail">
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>Event #{openEvent}</strong>
                <button onClick={() => setOpenEvent(null)}>✕</button>
              </div>
              <div style={{ fontSize: 13 }}>{eventCard ? `${eventCard.type} — ${eventCard.title}` : 'Loading…'}</div>
            </div>
          )}
        </div>
      </div>
      <Timeline date={timelineDate} setDate={setTimelineDate} />
    </div>
  );

  async function fetchEvent(id: number) {
    try {
      const res = await fetch(API_BASE + `/api/events/${id}`);
      const j = await res.json();
      setEventCard({ title: j.title, type: `${j.type} · ${j.confidence}` });
      setFlyTo({ lon: j.longitude, lat: j.latitude, zoom: 8, key: Date.now() });
    } catch {
      setEventCard({ title: 'Failed to load', type: '' });
    }
  }
}

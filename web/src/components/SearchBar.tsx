import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export default function SearchBar({ onFly }: { onFly: (lon: number, lat: number, zoom?: number) => void }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const conflicts = useQuery({ queryKey: ['search-conf', q], queryFn: () => api.conflicts({ search: q, page_size: 5 }), enabled: q.length > 1 });
  const events = useQuery({ queryKey: ['search-ev', q], queryFn: () => api.events({ search: q, page_size: 5 }), enabled: q.length > 1 });
  const countries = useQuery({ queryKey: ['search-co', q], queryFn: () => api.countries(q), enabled: q.length > 1 });

  return (
    <div style={{ position: 'relative', minWidth: 220 }}>
      <input placeholder="Search country, city, conflict, event…" value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
      {open && q.length > 1 && (
        <div className="searchresults">
          {(countries.data?.items || []).map((c) => (
            <div key={'c' + c.id} onClick={() => { if (c.lon && c.lat) onFly(c.lon, c.lat, 5); setOpen(false); }}>
              🌍 {c.name}{c.capital ? ` — ${c.capital}` : ''}
            </div>
          ))}
          {(conflicts.data?.items || []).map((c) => (
            <div key={'k' + c.id} onClick={() => {
              const g = c.geometry;
              if (g && g.type === 'Point') {
                const [lon, lat] = g.coordinates as [number, number];
                onFly(lon, lat, 6);
              } else onFly(20, 30, 2);
              setOpen(false);
            }}>⚔ {c.name}</div>
          ))}
          {(events.data?.items || []).map((e) => (
            <div key={'e' + e.id} onClick={() => { onFly(e.longitude, e.latitude, 8); setOpen(false); }}>
              ● {e.title}
            </div>
          ))}
          {(!conflicts.data && !events.data && !countries.data) && <div>Searching…</div>}
        </div>
      )}
    </div>
  );
}

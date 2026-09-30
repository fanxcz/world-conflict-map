import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Filters } from '../api/client';
import { API_BASE } from '../api/client';

export interface MapViewProps {
  filters: Filters;
  timelineDate: string; // YYYY-MM-DD
  onSelectConflict: (id: number) => void;
  onSelectEvent: (id: number) => void;
  flyTo: { lon: number; lat: number; zoom?: number; key: number } | null;
  visibleLayers: Record<string, boolean>;
}

const BASE_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

function colorForConfidence(c: string): string {
  if (c === 'CONFIRMED') return '#ff5252';
  if (c === 'UNVERIFIED') return '#9aa6b8';
  return '#ffb300';
}

export default function MapView({ filters, timelineDate, onSelectConflict, onSelectEvent, flyTo, visibleLayers }: MapViewProps) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const dateRef = useRef(timelineDate);
  dateRef.current = timelineDate;

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: BASE_STYLE,
      center: [20, 30],
      zoom: 1.6,
      maxZoom: 12,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    map.addControl(new maplibregl.FullscreenControl(), 'bottom-right');
    map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), 'bottom-right');
    map.dragRotate.enable();
    map.touchZoomRotate.enable();
    mapRef.current = map;

    map.on('load', () => {
      map.addSource('wcm', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, cluster: true, clusterMaxZoom: 10, clusterRadius: 45 });
      map.addLayer({ id: 'wcm-clusters', type: 'circle', source: 'wcm', filter: ['has', 'point_count'],
        paint: { 'circle-color': '#7a1f1a', 'circle-stroke-color': '#ff3b30', 'circle-stroke-width': 1.5, 'circle-radius': ['step', ['get', 'point_count'], 14, 20, 20, 60, 28], 'circle-opacity': 0.92 } });
      map.addLayer({ id: 'wcm-cluster-count', type: 'symbol', source: 'wcm', filter: ['has', 'point_count'],
        layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 11 }, paint: { 'text-color': '#fff' } });
      map.addLayer({ id: 'wcm-points', type: 'circle', source: 'wcm', filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': ['match', ['get', 'confidence'], 'CONFIRMED', '#ff3b30', 'UNVERIFIED', '#8b96a5', '#ffb300'],
          'circle-radius': 6, 'circle-stroke-color': '#0a0d12', 'circle-stroke-width': 2, 'circle-opacity': 0.95,
        } });
      map.addSource('wcm-poly', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'wcm-poly-fill', type: 'fill', source: 'wcm-poly', paint: { 'fill-color': ['coalesce', ['get', 'color'], '#ff3b30'], 'fill-opacity': 0.18 } });
      // frontline glow: wide blurred red casing under a crisp dashed core
      map.addLayer({ id: 'wcm-poly-glow', type: 'line', source: 'wcm-poly',
        paint: { 'line-color': ['coalesce', ['get', 'color'], '#ff3b30'], 'line-width': 7, 'line-opacity': 0.25, 'line-blur': 3 } });
      map.addLayer({ id: 'wcm-poly-line', type: 'line', source: 'wcm-poly',
        paint: { 'line-color': ['coalesce', ['get', 'color'], '#ff3b30'], 'line-width': 2.5, 'line-dasharray': [3, 1.5] } });

      map.on('click', 'wcm-points', (e) => {
        const f = e.features?.[0] as unknown as { properties: { kind: string; id: number } } | undefined;
        if (!f) return;
        if (f.properties.kind === 'event') onSelectEvent(f.properties.id);
        else if (f.properties.kind === 'conflict') onSelectConflict(f.properties.id);
      });
      map.on('click', 'wcm-poly-fill', (e) => {
        const f = e.features?.[0] as unknown as { properties: { conflict_id?: number } } | undefined;
        if (f?.properties.conflict_id) onSelectConflict(Number(f.properties.conflict_id));
      });
      void refresh();
    });

    async function refresh() {
      const m = mapRef.current;
      if (!m || !m.isStyleLoaded()) return;
      const f = filtersRef.current;
      const params = new URLSearchParams();
      if (f.conflictId) params.set('conflict_id', f.conflictId);
      if (dateRef.current) params.set('date', dateRef.current);
      try {
        const res = await fetch(API_BASE + '/api/map/geojson?' + params.toString());
        const fc = (await res.json()) as GeoJSON.FeatureCollection;
        let feats = fc.features as GeoJSON.Feature[];
        // client-side filters (type/confidence/search/region handled server-side partially)
        if (f.eventType) feats = feats.filter((x) => (x.properties as { type?: string })?.type === f.eventType || (x.properties as { kind?: string })?.kind !== 'event');
        if (f.confidence) feats = feats.filter((x) => (x.properties as { confidence?: string })?.confidence === f.confidence || (x.properties as { kind?: string })?.kind !== 'event');
        if (f.search) {
          const s = f.search.toLowerCase();
          feats = feats.filter((x) => JSON.stringify(x.properties).toLowerCase().includes(s));
        }
        const pts = feats.filter((x) => x.geometry.type === 'Point');
        const poly = feats.filter((x) => x.geometry.type !== 'Point');
        (m.getSource('wcm') as maplibregl.GeoJSONSource)?.setData({ type: 'FeatureCollection', features: pts as never });
        (m.getSource('wcm-poly') as maplibregl.GeoJSONSource)?.setData({ type: 'FeatureCollection', features: poly as never });
      } catch {
        /* offline: keep last data */
      }
    }
    const t = window.setInterval(() => void refresh(), 4000);
    (map as unknown as { __refresh: () => void }).__refresh = () => void refresh();
    return () => {
      window.clearInterval(t);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // refresh on filter/date change
  useEffect(() => {
    const m = mapRef.current as unknown as { __refresh?: () => void } | null;
    m?.__refresh?.();
  }, [filters, timelineDate]);

  // layer visibility
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !m.isStyleLoaded()) return;
    const set = (id: string, on: boolean) => {
      if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    };
    set('wcm-points', visibleLayers['incidents'] !== false);
    set('wcm-clusters', visibleLayers['incidents'] !== false);
    set('wcm-cluster-count', visibleLayers['incidents'] !== false);
    const polyOn = (visibleLayers['conflict_zones'] !== false) || (visibleLayers['frontlines'] !== false) || (visibleLayers['movements'] !== false);
    set('wcm-poly-fill', polyOn);
    set('wcm-poly-glow', polyOn);
    set('wcm-poly-line', polyOn);
    // base-map groups (best effort: these ids exist in CARTO dark-matter)
    const baseMap: Record<string, string[]> = {
      countries: ['country_boundaries', 'country_labels'],
      borders: ['boundaries', 'country_boundaries'],
      capitals: ['place_capital', 'capital_labels'],
      cities: ['place_city', 'city_labels'],
      roads: ['roads', 'motorways', 'streets'],
      rivers: ['waterways', 'rivers'],
    };
    for (const [key, ids] of Object.entries(baseMap)) {
      const on = visibleLayers[key] !== false;
      for (const lid of ids) {
        try {
          if (m.getLayer(lid)) m.setLayoutProperty(lid, 'visibility', on ? 'visible' : 'none');
        } catch { /* ignore */ }
      }
    }
    void colorForConfidence;
  }, [visibleLayers]);

  useEffect(() => {
    if (flyTo && mapRef.current) {
      mapRef.current.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: flyTo.zoom ?? 6, duration: 1200 });
    }
  }, [flyTo]);

  return <div ref={ref} className="map" />;
}

export function resetViewFn(setFly: (v: { lon: number; lat: number; zoom?: number; key: number }) => void) {
  setFly({ lon: 20, lat: 30, zoom: 1.6, key: Date.now() });
}

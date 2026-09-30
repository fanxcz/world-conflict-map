# World Conflict Map

Independent information GIS platform for visualizing publicly documented armed conflicts and related events. Informational service — not a weapon-targeting system. Every event carries date, type, description, source, confirmation status (`CONFIRMED` / `REPORTED` / `UNVERIFIED`), coordinates and update time.

## Features (all working)

- **Web map** (MapLibre GL JS, custom dark style): zoom / pan / rotate / fullscreen / reset view / search / 11 layer toggles, clustering, bbox loading.
- **Conflicts**: active / historical / reported, regions (Europe, Middle East, Africa, Asia, Americas, Other), conflict cards with events + sources.
- **Events**: 10 types (clash, airstrike, artillery, explosion, infrastructure_damage, territorial_change, military_movement, ceasefire, diplomatic, humanitarian), confidence filter, date range, source filter.
- **Timeline**: date picker, range slider, prev/next day, play/pause, speeds 0.5x/1x/2x/5x; map state follows selected date.
- **Search**: country / city / conflict / event, fly-to on select.
- **Admin (`/admin`)**: JWT login, dashboard, conflict/event/source CRUD (kept for fixes,
  own objects, sourceless feeds, geometry correction, multi-source merge), visual GeoJSON
  map editor (point/line/polygon, color, type, edit, delete, save), audit log view.
- **Import pipeline (primary fill method)**: `/admin/sources` Data Sources Manager
  (RSS/Atom/JSON API/GeoJSON/CSV/XML + TEST/UPDATE NOW/ENABLE/DISABLE/scheduler),
  `/admin/imports` moderation (PENDING → APPROVE/EDIT/REJECT/MERGE/DUPLICATE),
  AUTO-PUBLISH OFF, provenance + versions + import logs + dashboard + STALE freshness.
  Only local `[DEMO SOURCE]` fixtures bundled; no real feeds scraped.
- **Backend**: FastAPI + PostgreSQL/PostGIS (docker) or SQLite (local), SQLAlchemy, Alembic, pagination / filtering / sorting / validation / error handling / rate limiting (slowapi) / CORS whitelist / logging / secure headers, JWT + bcrypt, roles admin/editor/viewer.
- **Android**: Kotlin + Jetpack Compose, same REST API, map (WebView + MapLibre), conflict list, filters, search, bottom-sheet details, timeline, sources, offline Room cache with `OFFLINE MODE` + `Last updated`, push-notification architecture (categories: new_conflict_update / important_event / status_changed; SAMPLE data never notifies).

All demo objects are explicitly marked `DEMO / SAMPLE DATA` / `[SAMPLE]`. No fictional real-world military events are presented as facts.

## Requirements

- Debian 13, Python 3.11+, Node 20+, Java 17+, Android SDK (platform 35, build-tools 34), Docker + Compose (for container run).
- Local quick run needs no Docker (SQLite fallback).

## Project structure

```
world-conflict-map/
  web/            # React+TS+Vite+MapLibre frontend
  backend/        # FastAPI app (app/api, models, schemas, services, auth, gis, main.py), alembic, seed.py, tests
  android/        # Kotlin/Compose app, ./gradlew assembleDebug
  data/geojson/   # sample GeoJSON
  docker-compose.yml  (.env.example, Makefile, README.md)
```

## Setup (.env)

```bash
cp .env.example .env
# edit JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, DATABASE_URL, CORS_ORIGINS
```

## Run with Docker

```bash
docker compose up -d --build
docker compose down
```

- Web: http://localhost:8080 · API: http://localhost:8000 · Docs: http://localhost:8000/docs (`/redoc` too) · Admin: http://localhost:8080/admin

## Host frontend on GitHub Pages (backend stays on your server)

Pages serves static files only, so the frontend is deployed there while the
FastAPI backend runs on your VPS/Render/Fly/etc. The build already uses
relative asset paths (`base: './'`) and hash routing, so no 404 hacks needed.

1. Deploy the backend publicly over **https** (Docker image in `backend/` works
   anywhere). Set `CORS_ORIGINS` to include your Pages URL, e.g.
   `https://<user>.github.io`.
2. In the GitHub repo go to Settings → Pages → Source: **GitHub Actions**.
3. Add a repository variable `VITE_API_URL` = `https://your-api-host` (no
   trailing slash). Push to `main` — workflow `.github/workflows/pages.yml`
   builds `web/` and publishes `dist/`.
4. Open `https://<user>.github.io/<repo>/#/` — map, `/admin`, `/admin/sources`,
   `/admin/imports` work through hash routes.

Security notes: the browser bundle is public by design — never put secrets in
`web/.env` (only the public `VITE_API_URL`). Keep `JWT_SECRET`/`ADMIN_PASSWORD`
server-side, use HTTPS everywhere, log in to `/admin` only over HTTPS, and keep
`AUTO APPROVE` off for feeds you don't fully trust.

## Local run (Debian 13, no Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example ../.env  # or export DATABASE_URL="sqlite:///./wcm.db"
.venv/bin/python seed.py
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Migrations (Postgres):

```bash
cd backend
DATABASE_URL=postgresql+psycopg2://wcm:wcm@localhost:5432/wcm alembic upgrade head
```

Seed:

```bash
cd backend
python seed.py  # creates admin + regions + SAMPLE conflicts/events/geometries
```

Frontend:

```bash
cd web
npm install
npm run dev      # http://localhost:5173 (proxies /api -> :8000)
npm run build    # dist/
```

Android:

```bash
cd android
./gradlew assembleDebug
# APK: android/app/build/outputs/apk/debug/app-debug.apk
```

On emulator use backend URL `http://10.0.2.2:8000` (default in app); on device set your LAN IP in Settings screen.

## Data import (moderated pipeline — primary fill method)

Workflow: add source → TEST → ENABLE → scheduler or UPDATE NOW → PENDING queue →
VIEW SOURCE → EDIT/APPROVE/REJECT/MERGE/MARK AS DUPLICATE → public map + API.
AUTO-PUBLISH is OFF by default; per-source AUTO APPROVE is opt-in only.
Public `/api/events` and `/api/map/geojson` serve APPROVED rows only.

- Admin UI: `/admin/sources` (Sources/Active/Errors/Pending/Approved/Rejected/Last update,
  TEST, UPDATE NOW with `Fetching...Parsing...Normalizing...Deduplicating...Finished`,
  ENABLE/DISABLE, per-source auto-approve toggle, ADD SOURCE with JSON mapping)
  and `/admin/imports` (PENDING cards with provenance, VIEW SOURCE, EDIT, APPROVE,
  REJECT, MERGE, MARK AS DUPLICATE, import logs).
- Supported feed types: RSS, Atom, JSON API (configurable field mapping +
  `items_path`), GeoJSON (all 6 geometry kinds), CSV, XML. New adapters implement
  `fetch()/parse()/normalize()/validate()` in `backend/app/importer/adapters.py`.
- Scheduler: in-process 60s polling thread (no Celery/Redis needed for MVP);
  intervals manual/5m/15m/30m/1h/6h/daily. Untrusted feeds: 15s timeout, 5MB cap,
  5-redirect limit, content-type check, no JS execution, secrets masked in API.
- Dedup: same `external_id` in source, or coords (≈2km) + time (≈36h) + title
  similarity; low-confidence hits stay PENDING as DUPLICATE CANDIDATE.
- No coordinates invented: items without coords/geometry become LOCATION_UNKNOWN
  and cannot be approved until an admin sets them. Base layers
  (countries/borders/cities/roads/rivers) are never mixed with event imports.
- History: per-item versions (WHO/WHEN/WHAT) at `GET /api/pending/{id}/history`
  and `GET /api/events/{id}/history`; freshness at `GET /api/freshness`
  (STALE badge after 48h). Dashboard: `GET /api/importer/dashboard`.
- Demo feeds (explicitly fictional `[DEMO SOURCE]`, disabled auto-approve):
  `data/sample/demo_rss.xml`, `demo_api.json`, `demo.geojson`, `demo.csv`
  (seeded automatically). No real external sources are bundled.

```bash
cd backend
python -m app.import_geojson ../data/geojson/sample_features.geojson [--conflict-id 1] [--layer conflict_zones]
```

Validates geometry/coordinates/properties/CRS bounds (WGS84); bad files return error JSON and never crash the server.

## API documentation

- Swagger: `GET /docs` · ReDoc: `GET /redoc`
- Health: `GET /api/health`
- Conflicts: `GET/POST /api/conflicts`, `GET/PUT/DELETE /api/conflicts/{id}` (query: `page,page_size,region,status,search,sort_by,sort_order`)
- Events: `GET/POST /api/events`, `GET/PUT/DELETE /api/events/{id}` (query: `page,page_size,conflict_id,event_type,confidence,search,date_from,date_to,bbox,minLon,minLat,maxLon,maxLat,source,sort_by,sort_order`)
- Sources: `GET /api/sources`, `POST /api/sources`, `PUT /api/sources/{id}`
- Regions: `GET /api/regions` · Countries: `GET /api/countries?search=`
- Map: `GET /api/map/geojson?layer=&bbox=&date=&conflict_id=`, `POST/PUT/DELETE /api/map/features`
- Timeline: `GET /api/timeline?date=YYYY-MM-DD&conflict_id=`
- Auth: `POST /api/auth/login`, `GET /api/auth/me` (Bearer JWT)
- Audit: `GET /api/audit-logs` (admin only)
- Import pipeline: `GET/POST /api/data-sources`, `GET/PUT/DELETE /api/data-sources/{id}`,
  `POST /api/data-sources/{id}/test|update|enable|disable`, `GET /api/imports`,
  `GET /api/imports/{id}`, `GET /api/pending`, `PUT /api/pending/{id}`,
  `POST /api/pending/{id}/approve|reject|merge|duplicate`,
  `GET /api/import-logs`, `GET /api/importer/dashboard`, `GET /api/freshness`
  (spec §23 `/api/sources*` feed aliases at `/api/sources/feeds`;
  bibliographic `/api/sources` unchanged)
- All responses JSON; errors `{detail: ...}`; 401/403/404/422/429 handled.

Auth roles: `admin` (all), `editor` (create/edit, no user list/audit), `viewer` (read-only).

## Security

Parameterized ORM queries (SQL-injection safe), Pydantic validation, XSS-safe React rendering + JSON-only API, secure headers (nosniff/DENY/no-referrer), CORS whitelist, JWT expiry (12h), bcrypt hashing (never plaintext), rate limiting 120/min, audit log of every admin mutation (user/action/object/timestamp/old/new).

## Tests & lint

```bash
cd backend && python -m pytest tests -q
cd web && npm run build && npx tsc --noEmit && npx eslint src --ext .ts,.tsx
cd android && ./gradlew assembleDebug
```

Backend tests cover: health, auth, permissions, conflict CRUD, event CRUD, sources linkage, filtering (region/status/bbox/confidence/search/pagination), GeoJSON validation, map geojson, timeline, audit visibility, SQL-injection resistance, importer adapters (RSS/JSON/GeoJSON/CSV), source CRUD/TEST/enable, UPDATE NOW pipeline, PENDING isolation from public API, LOCATION_UNKNOWN approve block + manual fix, dedup rerun, reject/merge/duplicate, history, dashboard/freshness, secrets masking.

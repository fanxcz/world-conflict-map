"""External source adapters.

Every adapter implements fetch() -> parse() -> normalize() -> validate().
Untrusted input: timeouts, size caps, redirect limits, no JS execution,
no full article text copying (title/description truncated, link kept).
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import html
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 15
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = ("http", "https", "file", "local")

EVENT_TYPES = {
    "clash",
    "airstrike",
    "artillery",
    "explosion",
    "infrastructure_damage",
    "territorial_change",
    "military_movement",
    "ceasefire",
    "diplomatic",
    "humanitarian",
}


@dataclass
class NormalizedEvent:
    external_id: str | None = None
    title: str = ""
    description: str | None = None
    event_type: str = "clash"
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict | None = None
    event_time: datetime | None = None
    published_at: datetime | None = None
    confidence: str = "REPORTED"
    source_url: str | None = None
    country: str | None = None
    raw_data: dict = field(default_factory=dict)


def fetch_url(url: str, headers: dict | None = None) -> tuple[bytes, str]:
    """Fetch with timeout/size/redirect limits. Supports local demo files."""
    if url.startswith("file://"):
        p = Path(url[7:])
        data = p.read_bytes()[:MAX_BYTES]
        return data, "application/octet-stream"
    if url.startswith("local:"):
        p = Path(url[6:])
        data = p.read_bytes()[:MAX_BYTES]
        return data, "application/octet-stream"
    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"unsupported URL scheme: {scheme}")
    with httpx.Client(timeout=TIMEOUT_S, max_redirects=MAX_REDIRECTS, follow_redirects=True) as client:
        r = client.get(url, headers=headers or {"User-Agent": "WCM-Importer/1.0"})
        ctype = r.headers.get("content-type", "").split(";")[0].strip()
        data = r.content[:MAX_BYTES]
        r.raise_for_status()
        return data, ctype


def strip_html(s: str | None, limit: int = 2000) -> str | None:
    if not s:
        return None
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


def parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    s = str(value).strip()
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).replace(tzinfo=None)
    except Exception:
        pass
    for cand in (s, s.replace("Z", ""), s.split("+")[0]):
        with contextlib.suppress(Exception):
            return datetime.fromisoformat(cand)
    return None


def coerce_float(v: object) -> float | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return None


def guess_type(text: str) -> str:
    t = text.lower()
    for k in (
        "ceasefire",
        "humanitarian",
        "diplomatic",
        "airstrike",
        "artillery",
        "explosion",
        "territorial_change",
        "military_movement",
        "infrastructure_damage",
        "clash",
    ):
        if k.replace("_", " ") in t or k in t:
            return k
    return "clash"


class DataSourceAdapter:
    source_type = "base"

    def fetch(self, url: str, config: dict | None) -> tuple[bytes, str]:
        return fetch_url(url, (config or {}).get("headers"))

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        raise NotImplementedError

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        raise NotImplementedError

    def validate(self, ev: NormalizedEvent) -> tuple[bool, str]:
        if not ev.title or len(ev.title.strip()) < 2:
            return False, "empty title"
        if ev.event_type not in EVENT_TYPES:
            ev.event_type = "clash"
        if ev.confidence not in ("CONFIRMED", "REPORTED", "UNVERIFIED"):
            ev.confidence = "REPORTED"
        if ev.latitude is not None and not (-90 <= ev.latitude <= 90):
            return False, "latitude out of range"
        if ev.longitude is not None and not (-180 <= ev.longitude <= 180):
            return False, "longitude out of range"
        if ev.geometry is not None:
            from app.gis.validation import validate_geometry

            ok, msg = validate_geometry(ev.geometry)
            if not ok:
                return False, f"bad geometry: {msg}"
        return True, "ok"


# ---------------- RSS / Atom ----------------


def _rss_items(root: ET.Element) -> list[dict]:
    def child_text(el: ET.Element, tag: str) -> str | None:
        c = el.find(tag)
        return c.text.strip() if c is not None and c.text else None

    items: list[dict] = []
    for it in root.findall(".//item")[:500]:
        items.append(
            {
                "external_id": child_text(it, "guid") or child_text(it, "link") or child_text(it, "title"),
                "title": child_text(it, "title") or "",
                "description": child_text(it, "description"),
                "url": child_text(it, "link"),
                "published_at": child_text(it, "pubDate"),
                "publisher": None,
            }
        )
    if items:
        return items
    ns = {"a": "http://www.w3.org/2005/Atom"}

    def atom_text(e: ET.Element, tag: str) -> str | None:
        el = e.find(f"a:{tag}", ns)
        if el is None:
            el = e.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
        return el.text.strip() if el is not None and el.text else None

    for e in root.findall("a:entry", ns)[:500] + root.findall(".//{http://www.w3.org/2005/Atom}entry")[:500]:
        link = None
        lel = e.find("a:link", ns)
        if lel is not None:
            link = lel.get("href")
        items.append(
            {
                "external_id": atom_text(e, "id") or link or atom_text(e, "title"),
                "title": atom_text(e, "title") or "",
                "description": atom_text(e, "summary"),
                "url": link,
                "published_at": atom_text(e, "published") or atom_text(e, "updated"),
                "publisher": None,
            }
        )
    return items


class RssAdapter(DataSourceAdapter):
    source_type = "rss"

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        try:
            root = ET.fromstring(payload)
        except Exception as exc:
            raise ValueError(f"invalid RSS/Atom XML: {exc}") from exc
        return _rss_items(root)

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        title = strip_html(str(item.get("title") or ""), 500) or "Untitled"
        # RSS items carry no coordinates -> LOCATION_UNKNOWN downstream.
        return NormalizedEvent(
            external_id=str(item.get("external_id") or item.get("url") or title)[:255],
            title=title,
            description=strip_html(item.get("description")),
            event_type=guess_type(title + " " + str(item.get("description") or "")),
            event_time=parse_dt(item.get("published_at")),
            published_at=parse_dt(item.get("published_at")),
            source_url=item.get("url"),
            raw_data={k: str(v)[:1000] for k, v in item.items() if v is not None},
        )


class AtomAdapter(RssAdapter):
    source_type = "atom"


# ---------------- JSON API (configurable mapping) ----------------


class JsonApiAdapter(DataSourceAdapter):
    source_type = "json_api"

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        try:
            data = json.loads(payload.decode("utf-8", "replace"))
        except Exception as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        cfg = config or {}
        items_path = cfg.get("items_path", "")
        node: object = data
        if items_path:
            for part in items_path.split("."):
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    node = None
                    break
        if isinstance(node, dict) and "items" in node:
            node = node["items"]
        if isinstance(node, dict) and "features" in node:
            node = node["features"]
        if not isinstance(node, list):
            raise TypeError("JSON mapping: expected a list (set items_path, e.g. 'data.items')")
        out: list[dict] = []
        for it in node[:2000]:
            if isinstance(it, dict):
                out.append(it)
        return out

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        m = (config or {}).get("mapping", {}) or {}

        def g(*names: str) -> object:
            for n in names:
                if n in item and item[n] not in (None, ""):
                    return item[n]
            return None

        lat = coerce_float(g(m.get("latitude", "latitude"), "event_latitude", "lat", "y"))
        lon = coerce_float(g(m.get("longitude", "longitude"), "event_longitude", "lon", "lng", "x"))
        title = str(g(m.get("title", "title"), "name", "headline") or "Untitled")[:500]
        geom = g(m.get("geometry", "geometry"), "geom")
        geometry = geom if isinstance(geom, dict) and "type" in geom else None
        raw_type = str(g(m.get("type", "type"), "event_type", "category") or "clash").lower()
        etype = raw_type if raw_type in EVENT_TYPES else guess_type(title)
        return NormalizedEvent(
            external_id=str(g("external_id", "id", "guid") or title)[:255],
            title=strip_html(title, 500) or "Untitled",
            description=strip_html(str(g(m.get("description", "description"), "summary", "text") or ""))
            if g(m.get("description", "description"), "summary", "text")
            else None,
            event_type=etype,
            latitude=lat,
            longitude=lon,
            geometry=geometry,
            event_time=parse_dt(g(m.get("date", "date"), "event_time", "published_at", "timestamp")),
            published_at=parse_dt(g("published_at", "pubDate", "date")),
            source_url=str(g(m.get("source", "source"), "url", "link") or "") or None,
            country=str(g("country") or "") or None,
            raw_data={k: str(v)[:1000] for k, v in item.items()},
        )


# ---------------- GeoJSON ----------------


class GeoJsonAdapter(DataSourceAdapter):
    source_type = "geojson"

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        try:
            data = json.loads(payload.decode("utf-8", "replace"))
        except Exception as exc:
            raise ValueError(f"invalid GeoJSON: {exc}") from exc
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            feats = data.get("features", [])
            return [f for f in feats if isinstance(f, dict)][:2000]
        if isinstance(data, dict) and data.get("type") == "Feature":
            return [data]
        raise ValueError("GeoJSON root must be FeatureCollection/Feature")

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        geom = item.get("geometry") if isinstance(item.get("geometry"), dict) else None
        props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        lat = lon = None
        if geom and geom.get("type") == "Point":
            c = geom.get("coordinates") or []
            if len(c) == 2:
                lon, lat = coerce_float(c[0]), coerce_float(c[1])
        title = str(props.get("name") or props.get("title") or item.get("id") or "GeoJSON feature")[:500]
        return NormalizedEvent(
            external_id=str(props.get("id") or item.get("id") or title)[:255],
            title=strip_html(title, 500) or "Untitled",
            description=strip_html(str(props.get("description") or "")) if props.get("description") else None,
            event_type=str(props.get("event_type") or props.get("type") or "clash").lower()
            if str(props.get("event_type") or props.get("type") or "") in EVENT_TYPES
            else guess_type(title),
            latitude=lat,
            longitude=lon,
            geometry=geom,
            event_time=parse_dt(props.get("event_time") or props.get("date")),
            published_at=parse_dt(props.get("published_at")),
            source_url=props.get("url"),
            raw_data={"properties": {k: str(v)[:500] for k, v in props.items()}},
        )


# ---------------- CSV ----------------


class CsvAdapter(DataSourceAdapter):
    source_type = "csv"

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        cfg = config or {}
        text = payload.decode("utf-8", "replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=cfg.get("delimiter", ","))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return [dict(r) for _, r in zip(range(2000), reader)]

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        m = (config or {}).get("mapping", {}) or {}

        def g(*names: str) -> object:
            for n in names:
                if n in item and item[n] not in (None, ""):
                    return item[n]
            return None

        title = str(g(m.get("title", "title"), "name") or "Untitled")[:500]
        return NormalizedEvent(
            external_id=str(g("external_id", "id") or title)[:255],
            title=strip_html(title, 500) or "Untitled",
            description=strip_html(str(g(m.get("description", "description"), "desc") or ""))
            if g(m.get("description", "description"), "desc")
            else None,
            event_type="clash",
            latitude=coerce_float(g(m.get("latitude", "latitude"), "lat")),
            longitude=coerce_float(g(m.get("longitude", "longitude"), "lon", "lng")),
            event_time=parse_dt(g(m.get("date", "date"), "event_time")),
            published_at=parse_dt(g("published_at")),
            source_url=str(g("url", "link") or "") or None,
            raw_data={k: str(v)[:500] for k, v in item.items()},
        )


# ---------------- XML (generic) ----------------


class XmlAdapter(DataSourceAdapter):
    source_type = "xml"

    def parse(self, payload: bytes, config: dict | None) -> list[dict]:
        cfg = config or {}
        try:
            root = ET.fromstring(payload)
        except Exception as exc:
            raise ValueError(f"invalid XML: {exc}") from exc
        item_tag = cfg.get("item_tag", "item")
        fields = cfg.get("fields", ["title", "description", "link", "pubDate", "lat", "lon"])
        out: list[dict] = []
        for it in root.findall(f".//{item_tag}")[:1000]:
            d: dict = {}
            for f in fields:
                el = it.find(f)
                d[f] = el.text.strip() if el is not None and el.text else None
            d["external_id"] = d.get("guid") or d.get("link") or d.get("title")
            d["url"] = d.get("link")
            out.append(d)
        return out

    def normalize(self, item: dict, config: dict | None) -> NormalizedEvent:
        title = strip_html(str(item.get("title") or "Untitled"), 500) or "Untitled"
        return NormalizedEvent(
            external_id=str(item.get("external_id") or title)[:255],
            title=title,
            description=strip_html(item.get("description")),
            event_type=guess_type(title),
            latitude=coerce_float(item.get("lat")),
            longitude=coerce_float(item.get("lon") or item.get("lng")),
            event_time=parse_dt(item.get("pubDate") or item.get("date")),
            published_at=parse_dt(item.get("pubDate")),
            source_url=item.get("url"),
            raw_data={k: str(v)[:500] for k, v in item.items() if v is not None},
        )


ADAPTERS: dict[str, DataSourceAdapter] = {
    "rss": RssAdapter(),
    "atom": AtomAdapter(),
    "json_api": JsonApiAdapter(),
    "geojson": GeoJsonAdapter(),
    "csv": CsvAdapter(),
    "xml": XmlAdapter(),
}


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

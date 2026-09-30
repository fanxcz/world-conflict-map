"""Deduplication: same incident reported by several outlets -> one pending item.

Never auto-delete potentially different events. Low-confidence matches are
flagged DUPLICATE CANDIDATE for the admin instead of being merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models import Event, PendingItem

COORD_KM_TOL = 2.0
TIME_H_TOL = 36
TITLE_SIM_HIGH = 0.82
TITLE_SIM_LOW = 0.55


@dataclass
class DedupResult:
    is_duplicate: bool = False
    candidate: bool = False
    match_event_id: int | None = None
    match_pending_id: int | None = None
    candidate_ids: list[int] | None = None
    reason: str = ""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    try:
        return abs((a - b).total_seconds()) / 3600.0
    except Exception:
        return None


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def check_duplicate(
    db: Session,
    source_id: int,
    external_id: str | None,
    title: str,
    lat: float | None,
    lon: float | None,
    event_time: datetime | None,
) -> DedupResult:
    # 1) exact external_id within same source -> hard duplicate
    if external_id:
        row = (
            db.query(PendingItem)
            .filter(PendingItem.source_id == source_id, PendingItem.external_id == external_id)
            .filter(PendingItem.status.in_(("PENDING", "APPROVED")))
            .first()
        )
        if row:
            return DedupResult(True, False, None, row.id, None, "same external_id in this source")
    # 2) fuzzy against approved events + pending items
    cands: list[tuple[float, str, int]] = []
    q_events = db.query(Event).order_by(Event.id.desc()).limit(2000).all()
    q_pending = (
        db.query(PendingItem).filter(PendingItem.status == "PENDING").order_by(PendingItem.id.desc()).limit(1000).all()
    )
    for e in q_events:
        s = _sim(title, e.title or "")
        geo_ok, time_ok = True, True
        if lat is not None and lon is not None:
            geo_ok = _haversine_km(lat, lon, e.latitude, e.longitude) <= COORD_KM_TOL
        h = _hours(event_time, e.event_time)
        if h is not None:
            time_ok = h <= TIME_H_TOL
        if s >= TITLE_SIM_HIGH and geo_ok and time_ok:
            return DedupResult(True, False, e.id, None, None, f"matches EVENT #{e.id} (sim={s:.2f})")
        if s >= TITLE_SIM_LOW and (geo_ok or h is not None and h <= TIME_H_TOL):
            cands.append((s, "event", e.id))
    for p in q_pending:
        s = _sim(title, p.title or "")
        geo_ok, time_ok = True, True
        if lat is not None and lon is not None and p.latitude is not None and p.longitude is not None:
            geo_ok = _haversine_km(lat, lon, p.latitude, p.longitude) <= COORD_KM_TOL
        h = _hours(event_time, p.event_time)
        if h is not None:
            time_ok = h <= TIME_H_TOL
        if s >= TITLE_SIM_HIGH and geo_ok and time_ok:
            return DedupResult(True, False, None, p.id, None, f"matches PENDING #{p.id} (sim={s:.2f})")
        if s >= TITLE_SIM_LOW and (geo_ok or (h is not None and h <= TIME_H_TOL)):
            cands.append((s, "pending", p.id))
    if cands:
        cands.sort(reverse=True)
        ids = [i for _, _, i in cands[:5]]
        return DedupResult(False, True, None, None, ids, "possible duplicates need review")
    return DedupResult(False, False, None, None, None, "")

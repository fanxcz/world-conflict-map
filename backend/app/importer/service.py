"""Import pipeline: FETCH -> VALIDATE -> PARSE -> NORMALIZE -> DEDUP -> MODERATION -> APPROVE -> PUBLIC."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.importer.adapters import ADAPTERS, content_hash
from app.importer.dedup import check_duplicate
from app.models import (
    DataSource,
    Event,
    EventHistory,
    EventSource,
    ImportLog,
    PendingItem,
    PendingItemHistory,
    RawImport,
    Source,
)
from app.services.audit import write_audit


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def run_source(db: Session, source_id: int, triggered_by: str = "manual") -> dict:
    src = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not src:
        raise ValueError("source not found")
    log = ImportLog(source_id=src.id, started_at=_now(), status="RUNNING")
    db.add(log)
    db.flush()
    stats = {"fetched": 0, "new": 0, "duplicates": 0, "invalid": 0, "pending_review": 0}
    try:
        adapter = ADAPTERS.get(src.source_type)
        if not adapter:
            raise ValueError(f"no adapter for type {src.source_type!r}")
        if not src.enabled:
            raise ValueError("source is disabled")
        payload, ctype = adapter.fetch(src.url, src.fetch_config or {})
        _ = ctype
        raw = RawImport(
            source_id=src.id,
            fetched_at=_now(),
            content_hash=content_hash(payload),
            raw_payload={"bytes": len(payload), "note": "payload stored trimmed; full blob not kept"},
        )
        db.add(raw)
        db.flush()
        try:
            items = adapter.parse(payload, src.fetch_config or {})
        except Exception as exc:
            raise ValueError(f"parse error: {exc}") from exc
        stats["fetched"] = len(items)
        for it in items:
            try:
                nev = adapter.normalize(it, src.fetch_config or {})
                ok, _ = adapter.validate(nev)
            except Exception:
                stats["invalid"] += 1
                continue
            if not ok:
                stats["invalid"] += 1
                continue
            loc_known = nev.latitude is not None and nev.longitude is not None
            if nev.geometry is None and not loc_known:
                location_status = "LOCATION_UNKNOWN"  # never invent coords from a place name
            else:
                location_status = "KNOWN"
            dd = check_duplicate(db, src.id, nev.external_id, nev.title, nev.latitude, nev.longitude, nev.event_time)
            if dd.is_duplicate:
                stats["duplicates"] += 1
                continue
            pend = PendingItem(
                source_id=src.id,
                raw_import_id=raw.id,
                external_id=nev.external_id,
                title=nev.title[:500],
                description=nev.description,
                event_type=nev.event_type,
                latitude=nev.latitude,
                longitude=nev.longitude,
                geometry=nev.geometry,
                location_status=location_status,
                event_time=nev.event_time or nev.published_at or _now(),
                published_at=nev.published_at,
                confidence="REPORTED",
                source_url=nev.source_url,
                status="PENDING",
                duplicate_candidate=dd.candidate,
                candidate_ids={"ids": dd.candidate_ids, "reason": dd.reason} if dd.candidate else None,
                provenance={
                    "source_name": src.name,
                    "publisher": src.publisher,
                    "original_url": nev.source_url,
                    "fetched": _now().isoformat(),
                    "published": nev.published_at.isoformat() if nev.published_at else None,
                    "imported": _now().isoformat(),
                    "triggered_by": triggered_by,
                    "external_id": nev.external_id,
                },
            )
            db.add(pend)
            db.flush()
            db.add(
                PendingItemHistory(
                    pending_id=pend.id,
                    version=1,
                    who=triggered_by,
                    changes={"created": True, "reason": dd.reason or "new"},
                )
            )
            stats["new"] += 1
            if dd.candidate:
                stats["pending_review"] += 1
            # trusted per-source auto-approve (only when explicitly enabled)
            if src.auto_approve and not dd.candidate and location_status == "KNOWN":
                _approve(db, pend, triggered_by + ":auto-approve", src)
        src.items_received = (src.items_received or 0) + stats["fetched"]
        src.last_run_at = _now()
        src.last_success_at = _now()
        src.last_error = None
        src.status = "ACTIVE" if src.enabled else "DISABLED"

        from app.models import INTERVALS

        secs = INTERVALS.get(src.update_interval, 0)
        if secs:
            src.next_run_at = datetime.fromtimestamp(_now().timestamp() + secs, tz=UTC).replace(tzinfo=None)
        else:
            src.next_run_at = None
        log.status = "SUCCESS"
    except Exception as exc:
        log.status = "ERROR"
        log.error = str(exc)[:2000]
        src.last_error = str(exc)[:2000]
        src.error_count = (src.error_count or 0) + 1
        src.status = "ERROR"
        src.last_run_at = _now()
    finally:
        log.finished_at = _now()
        log.fetched, log.new, log.duplicates, log.invalid = (
            stats["fetched"],
            stats["new"],
            stats["duplicates"],
            stats["invalid"],
        )
        log.pending_review = stats["pending_review"]
        db.commit()
    return {
        "source_id": src.id,
        **stats,
        "status": log.status,
        "error": log.error,
        "message": f"Fetched: {stats['fetched']} New: {stats['new']} Duplicates: {stats['duplicates']} Invalid: {stats['invalid']} Pending review: {stats['pending_review']}",
    }


def test_source(db: Session, source_id: int) -> dict:
    src = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not src:
        raise ValueError("source not found")
    adapter = ADAPTERS.get(src.source_type)
    if not adapter:
        return {"connection": "OK", "error": f"no adapter for {src.source_type}"}
    try:
        payload, ctype = adapter.fetch(src.url, src.fetch_config or {})
        items = adapter.parse(payload, src.fetch_config or {})
        with_coords = 0
        for it in items[:200]:
            try:
                nev = adapter.normalize(it, src.fetch_config or {})
                if nev.latitude is not None and nev.longitude is not None:
                    with_coords += 1
            except Exception:
                pass
        return {
            "connection": "OK",
            "format": src.source_type.upper(),
            "items": len(items),
            "parsing": "OK",
            "coordinates": with_coords,
            "without_coordinates": len(items) - with_coords,
            "bytes": len(payload),
            "content_type": ctype,
        }
    except Exception as exc:
        return {"connection": "FAIL", "error": str(exc)[:1000]}


def _get_or_make_source(db: Session, src: DataSource) -> Source:
    row = db.query(Source).filter(Source.title == src.name).first()
    if row:
        return row
    row = Source(
        title=src.name,
        publisher=src.publisher or "External feed",
        url=src.url,
        reliability_note=f"trust={src.trust_level}",
    )
    db.add(row)
    db.flush()
    return row


def _approve(db: Session, pend: PendingItem, who: str, src: DataSource | None = None) -> Event:
    src = src or db.query(DataSource).filter(DataSource.id == pend.source_id).first()
    lat, lon = pend.latitude, pend.longitude
    if (lat is None or lon is None) and pend.geometry:
        try:
            from shapely.geometry import shape as _shape

            c = _shape(pend.geometry).centroid
            lon, lat = float(c.x), float(c.y)
        except Exception:
            pass
    if lat is None or lon is None:
        raise ValueError("LOCATION_UNKNOWN: set coordinates (manual fix) before approving")
    ev = Event(
        conflict_id=pend.conflict_id,
        type=pend.event_type or "clash",
        title=pend.title,
        description=(pend.description or "") + f"\n\n[Provenance: {pend.source_url or (src.name if src else '')}]",
        latitude=lat,
        longitude=lon,
        event_time=pend.event_time or _now(),
        confidence="REPORTED",
        is_sample=bool(src.is_demo) if src else False,
    )
    db.add(ev)
    db.flush()
    if src:
        srow = _get_or_make_source(db, src)
        db.add(EventSource(event_id=ev.id, source_id=srow.id))
    db.add(EventHistory(event_id=ev.id, version=1, who=who, changes={"from_pending": pend.id, "title": pend.title}))
    pend.status = "APPROVED"
    pend.approved_event_id = ev.id
    pend.reviewed_by = who
    pend.reviewed_at = _now()
    pend.version = (pend.version or 1) + 1
    db.add(
        PendingItemHistory(
            pending_id=pend.id, version=pend.version, who=who, changes={"approved": True, "event_id": ev.id}
        )
    )
    if src:
        src.items_approved = (src.items_approved or 0) + 1
    write_audit(
        db,
        who if isinstance(who, str) else getattr(who, "email", str(who)),
        "APPROVE",
        "PENDING_ITEM",
        pend.id,
        {"status": "PENDING"},
        {"status": "APPROVED", "event_id": ev.id},
    )
    db.flush()
    return ev


def approve_pending(
    db: Session, pending_id: int, who: str, conflict_id: int | None = None, edits: dict | None = None
) -> Event:
    pend = db.query(PendingItem).filter(PendingItem.id == pending_id).first()
    if not pend:
        raise ValueError("pending item not found")
    if pend.status != "PENDING":
        raise ValueError(f"item is {pend.status}, only PENDING can be approved")
    if pend.location_status == "LOCATION_UNKNOWN" and (pend.latitude is None or pend.longitude is None):
        raise ValueError("LOCATION_UNKNOWN: set coordinates (manual fix) before approving")
    if conflict_id is not None:
        pend.conflict_id = conflict_id
    if edits:
        for k in ("title", "description", "event_type", "latitude", "longitude", "event_time", "confidence"):
            if k in edits and edits[k] is not None:
                setattr(pend, k, edits[k])
        pend.version = (pend.version or 1) + 1
        db.add(PendingItemHistory(pending_id=pend.id, version=pend.version, who=who, changes={"edit": edits}))
    src = db.query(DataSource).filter(DataSource.id == pend.source_id).first() if pend.source_id else None
    ev = _approve(db, pend, who, src)
    db.commit()
    return ev


def reject_pending(db: Session, pending_id: int, who: str, reason: str = "") -> PendingItem:
    pend = db.query(PendingItem).filter(PendingItem.id == pending_id).first()
    if not pend:
        raise ValueError("pending item not found")
    pend.status = "REJECTED"
    pend.reviewed_by = who
    pend.reviewed_at = _now()
    db.add(
        PendingItemHistory(
            pending_id=pend.id, version=(pend.version or 1) + 1, who=who, changes={"rejected": True, "reason": reason}
        )
    )
    write_audit(db, who, "REJECT", "PENDING_ITEM", pend.id, {"status": "PENDING"}, {"status": "REJECTED"})
    db.commit()
    return pend


def mark_duplicate(db: Session, pending_id: int, who: str, of_id: int, kind: str = "event") -> PendingItem:
    pend = db.query(PendingItem).filter(PendingItem.id == pending_id).first()
    if not pend:
        raise ValueError("pending item not found")
    pend.status = "DUPLICATE"
    pend.duplicate_candidate = False
    pend.duplicate_of_event_id = of_id if kind == "event" else None
    pend.reviewed_by = who
    pend.reviewed_at = _now()
    db.add(
        PendingItemHistory(
            pending_id=pend.id, version=(pend.version or 1) + 1, who=who, changes={"duplicate_of": of_id, "kind": kind}
        )
    )
    # multi-source link: attach this feed as an extra source on the surviving event
    if kind == "event":
        ev = db.query(Event).filter(Event.id == of_id).first()
        src = db.query(DataSource).filter(DataSource.id == pend.source_id).first() if pend.source_id else None
        if ev and src:
            srow = _get_or_make_source(db, src)
            if (
                not db.query(EventSource)
                .filter(EventSource.event_id == ev.id, EventSource.source_id == srow.id)
                .first()
            ):
                db.add(EventSource(event_id=ev.id, source_id=srow.id))
    db.commit()
    return pend


def merge_pending(db: Session, pending_id: int, who: str, into_event_id: int) -> Event:
    """MERGE: copy missing fields/sources into existing event, close pending as MERGED."""
    pend = db.query(PendingItem).filter(PendingItem.id == pending_id).first()
    ev = db.query(Event).filter(Event.id == into_event_id).first()
    if not pend or not ev:
        raise ValueError("pending or event not found")
    changes: dict = {}
    if pend.description and not ev.description:
        ev.description = pend.description
        changes["description"] = "filled from pending"
    src = db.query(DataSource).filter(DataSource.id == pend.source_id).first() if pend.source_id else None
    if src:
        srow = _get_or_make_source(db, src)
        if not db.query(EventSource).filter(EventSource.event_id == ev.id, EventSource.source_id == srow.id).first():
            db.add(EventSource(event_id=ev.id, source_id=srow.id))
            changes["source_added"] = srow.title
    n = (db.query(EventHistory).filter(EventHistory.event_id == ev.id).count() or 0) + 1
    db.add(EventHistory(event_id=ev.id, version=n, who=who, changes={"merge_from_pending": pend.id, **changes}))
    pend.status = "MERGED"
    pend.reviewed_by = who
    pend.reviewed_at = _now()
    db.add(
        PendingItemHistory(
            pending_id=pend.id, version=(pend.version or 1) + 1, who=who, changes={"merged_into": into_event_id}
        )
    )
    db.commit()
    return ev

"""Data-source manager + moderation queue API.

Public map serves ONLY approved rows (events/map_features).
/api/pending* and /api/imports* require editor; dashboard/audit admin-visible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_editor
from app.database import get_db
from app.importer import service as svc
from app.models import (
    INTERVALS,
    PENDING_STATUS,
    SOURCE_TYPES,
    TRUST_LEVELS,
    DataSource,
    Event,
    EventHistory,
    ImportLog,
    PendingItem,
    PendingItemHistory,
    User,
)

router = APIRouter(tags=["importer"])

SECRET_KEYS = {"authorization", "api_key", "token", "password", "secret"}


def mask_config(cfg: dict | None) -> dict | None:
    if not cfg:
        return cfg
    out = dict(cfg)
    headers = dict(out.get("headers") or {})
    for k in list(headers):
        if k.lower() in SECRET_KEYS:
            headers[k] = "***"
    if headers:
        out["headers"] = headers
    if "auth" in out:
        out["auth"] = "***"
    return out


def src_out(s: DataSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "publisher": s.publisher,
        "url": s.url,
        "source_type": s.source_type,
        "type": s.source_type,
        "enabled": s.enabled,
        "auto_approve": s.auto_approve,
        "trust_level": s.trust_level,
        "update_interval": s.update_interval,
        "status": s.status,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_update": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_error": s.last_error,
        "error_count": s.error_count,
        "items_received": s.items_received,
        "items_approved": s.items_approved,
        "fetch_config": mask_config(s.fetch_config),
        "is_demo": s.is_demo,
    }


def pend_out(p: PendingItem, db: Session | None = None) -> dict:
    d = {
        "id": p.id,
        "source_id": p.source_id,
        "external_id": p.external_id,
        "title": p.title,
        "description": p.description,
        "event_type": p.event_type,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "geometry": p.geometry,
        "location_status": p.location_status,
        "event_time": p.event_time.isoformat() if p.event_time else None,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "confidence": p.confidence,
        "source_url": p.source_url,
        "conflict_id": p.conflict_id,
        "status": p.status,
        "duplicate_candidate": p.duplicate_candidate,
        "candidate_ids": p.candidate_ids,
        "duplicate_of_event_id": p.duplicate_of_event_id,
        "approved_event_id": p.approved_event_id,
        "provenance": p.provenance,
        "version": p.version,
        "reviewed_by": p.reviewed_by,
        "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if db is not None and p.source_id:
        s = db.query(DataSource).filter(DataSource.id == p.source_id).first()
        d["source_name"] = s.name if s else None
    return d


class SourceIn(BaseModel):
    name: str
    url: str
    source_type: str = "rss"
    publisher: str | None = None
    update_interval: str = "manual"
    enabled: bool = True
    auto_approve: bool = False
    trust_level: str = "UNKNOWN"
    fetch_config: dict | None = None

    @field_validator("source_type")
    @classmethod
    def _t(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
        return v

    @field_validator("trust_level")
    @classmethod
    def _tr(cls, v: str) -> str:
        if v not in TRUST_LEVELS:
            raise ValueError(f"trust_level must be one of {TRUST_LEVELS}")
        return v

    @field_validator("update_interval")
    @classmethod
    def _i(cls, v: str) -> str:
        if v not in INTERVALS:
            raise ValueError(f"update_interval must be one of {tuple(INTERVALS)}")
        return v


class SourcePatch(BaseModel):
    name: str | None = None
    url: str | None = None
    source_type: str | None = None
    publisher: str | None = None
    update_interval: str | None = None
    enabled: bool | None = None
    auto_approve: bool | None = None
    trust_level: str | None = None
    fetch_config: dict | None = None


# ---- data sources CRUD ----
@router.get("/data-sources", response_model=list)
def list_sources(db: Session = Depends(get_db), _u: User = Depends(get_current_user)):
    return [src_out(s) for s in db.query(DataSource).order_by(DataSource.id).all()]


@router.post("/data-sources", response_model=dict, status_code=201)
def create_source(payload: SourceIn, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    s = DataSource(**payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return src_out(s)


@router.get("/data-sources/{sid}", response_model=dict)
def get_source(sid: int, db: Session = Depends(get_db), _u: User = Depends(get_current_user)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "source not found")
    return src_out(s)


@router.put("/data-sources/{sid}", response_model=dict)
def update_source(sid: int, payload: SourcePatch, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "source not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return src_out(s)


@router.delete("/data-sources/{sid}", status_code=204)
def delete_source(sid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "source not found")
    db.delete(s)
    db.commit()


@router.post("/data-sources/{sid}/test", response_model=dict)
def test_src(sid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    try:
        return svc.test_source(db, sid)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/data-sources/{sid}/update", response_model=dict)
def update_now(sid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    try:
        return svc.run_source(db, sid, triggered_by=_u.email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/data-sources/{sid}/enable", response_model=dict)
def enable_src(sid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "source not found")
    s.enabled = True
    if s.status == "DISABLED":
        s.status = "NEVER_RUN"
    db.commit()
    return src_out(s)


@router.post("/data-sources/{sid}/disable", response_model=dict)
def disable_src(sid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    s = db.query(DataSource).filter(DataSource.id == sid).first()
    if not s:
        raise HTTPException(404, "source not found")
    s.enabled = False
    s.status = "DISABLED"
    db.commit()
    return src_out(s)


# ---- moderation queue ----
def _query_pending(db: Session, status: str | None, source_id: int | None, search: str | None):
    q = db.query(PendingItem).order_by(PendingItem.created_at.desc())
    if status:
        q = q.filter(PendingItem.status == status)
    if source_id is not None:
        q = q.filter(PendingItem.source_id == source_id)
    if search:
        like = f"%{search}%"
        q = q.filter(PendingItem.title.ilike(like))
    return q


@router.get("/imports", response_model=dict)
def list_imports(
    status: str | None = None,
    source_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _u: User = Depends(require_editor),
):
    if status and status not in PENDING_STATUS:
        raise HTTPException(400, f"status must be one of {PENDING_STATUS}")
    q = _query_pending(db, status, source_id, search)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [pend_out(p, db) for p in items], "total": total, "page": page, "page_size": page_size}


@router.get("/imports/{pid}", response_model=dict)
def get_import(pid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    p = db.query(PendingItem).filter(PendingItem.id == pid).first()
    if not p:
        raise HTTPException(404, "not found")
    out = pend_out(p, db)
    if p.raw_import_id:
        from app.models import RawImport

        r = db.query(RawImport).filter(RawImport.id == p.raw_import_id).first()
        out["raw_meta"] = {"id": r.id, "fetched_at": r.fetched_at.isoformat(), "hash": r.content_hash} if r else None
    return out


@router.get("/pending", response_model=dict)
def list_pending(
    source_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _u: User = Depends(require_editor),
):
    return list_imports(
        status="PENDING", source_id=source_id, search=search, page=page, page_size=page_size, db=db, _u=_u
    )


class ApproveIn(BaseModel):
    conflict_id: int | None = None
    edits: dict | None = None


@router.put("/pending/{pid}", response_model=dict)
def edit_pending(pid: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    p = db.query(PendingItem).filter(PendingItem.id == pid).first()
    if not p:
        raise HTTPException(404, "not found")
    if p.status != "PENDING":
        raise HTTPException(400, f"item is {p.status}")
    allowed = (
        "title",
        "description",
        "event_type",
        "latitude",
        "longitude",
        "geometry",
        "event_time",
        "confidence",
        "conflict_id",
        "source_url",
    )
    changes = {k: payload[k] for k in allowed if k in payload}
    for k, v in changes.items():
        setattr(p, k, v)
    p.version = (p.version or 1) + 1
    db.add(PendingItemHistory(pending_id=p.id, version=p.version, who=user.email, changes={"edit": changes}))
    db.commit()
    db.refresh(p)
    return pend_out(p, db)


@router.post("/pending/{pid}/approve", response_model=dict)
def approve(
    pid: int, payload: ApproveIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    try:
        ev = svc.approve_pending(
            db,
            pid,
            user.email,
            conflict_id=(payload.conflict_id if payload else None),
            edits=(payload.edits if payload else None),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"event_id": ev.id, "title": ev.title}


@router.post("/pending/{pid}/reject", response_model=dict)
def reject(pid: int, payload: dict | None = None, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    try:
        p = svc.reject_pending(db, pid, user.email, (payload or {}).get("reason", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return pend_out(p, db)


@router.post("/pending/{pid}/duplicate", response_model=dict)
def duplicate(pid: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    try:
        p = svc.mark_duplicate(db, pid, user.email, int(payload.get("of_id")), payload.get("kind", "event"))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc))
    return pend_out(p, db)


@router.post("/pending/{pid}/merge", response_model=dict)
def merge(pid: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    try:
        ev = svc.merge_pending(db, pid, user.email, int(payload.get("into_event_id")))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc))
    return {"event_id": ev.id}


@router.get("/pending/{pid}/history", response_model=list)
def pending_history(pid: int, db: Session = Depends(get_db), _u: User = Depends(require_editor)):
    rows = (
        db.query(PendingItemHistory)
        .filter(PendingItemHistory.pending_id == pid)
        .order_by(PendingItemHistory.version)
        .all()
    )
    return [
        {
            "version": r.version,
            "who": r.who,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "changes": r.changes,
        }
        for r in rows
    ]


@router.get("/events/{eid}/history", response_model=list)
def event_history(eid: int, db: Session = Depends(get_db), _u: User = Depends(get_current_user)):
    rows = db.query(EventHistory).filter(EventHistory.event_id == eid).order_by(EventHistory.version).all()
    return [
        {
            "version": r.version,
            "who": r.who,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "changes": r.changes,
        }
        for r in rows
    ]


# ---- logs / dashboard / freshness ----
@router.get("/import-logs", response_model=dict)
def import_logs(
    source_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    _u: User = Depends(require_editor),
):
    q = db.query(ImportLog).order_by(ImportLog.started_at.desc())
    if source_id is not None:
        q = q.filter(ImportLog.source_id == source_id)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": l.id,
                "source_id": l.source_id,
                "started_at": l.started_at.isoformat() if l.started_at else None,
                "finished_at": l.finished_at.isoformat() if l.finished_at else None,
                "status": l.status,
                "fetched": l.fetched,
                "new": l.new,
                "duplicates": l.duplicates,
                "invalid": l.invalid,
                "pending_review": l.pending_review,
                "error": l.error,
            }
            for l in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/importer/dashboard", response_model=dict)
def dashboard(db: Session = Depends(get_db), _u: User = Depends(get_current_user)):
    sources = db.query(DataSource).count()
    active = db.query(DataSource).filter(DataSource.enabled.is_(True)).count()
    errors = db.query(DataSource).filter(DataSource.status == "ERROR").count()
    pending = db.query(PendingItem).filter(PendingItem.status == "PENDING").count()
    day_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    approved_today = (
        db.query(PendingItem).filter(PendingItem.status == "APPROVED", PendingItem.reviewed_at >= day_ago).count()
    )
    rejected_today = (
        db.query(PendingItem).filter(PendingItem.status == "REJECTED", PendingItem.reviewed_at >= day_ago).count()
    )
    last_ok = (
        db.query(DataSource)
        .filter(DataSource.last_success_at.isnot(None))
        .order_by(DataSource.last_success_at.desc())
        .first()
    )
    ev = db.query(Event).order_by(Event.updated_at.desc()).first()
    return {
        "sources": sources,
        "active": active,
        "errors": errors,
        "pending": pending,
        "approved_today": approved_today,
        "rejected_today": rejected_today,
        "last_update": last_ok.last_success_at.isoformat() if last_ok and last_ok.last_success_at else None,
        "public_last_updated": ev.updated_at.isoformat() if ev and ev.updated_at else None,
    }


@router.get("/freshness", response_model=dict)
def freshness(db: Session = Depends(get_db)):
    ev = db.query(Event).order_by(Event.updated_at.desc()).first()
    last = ev.updated_at if ev else None
    stale = bool(last and (datetime.now(UTC).replace(tzinfo=None) - last) > timedelta(hours=48))
    return {
        "last_updated": last.isoformat() + "Z" if last else None,
        "stale": stale,
        "note": "STALE: data older than 48h, do not treat as current" if stale else "Public data: APPROVED items only",
    }


# Spec §23 compat aliases: /api/sources/* for feed manager (bibliographic sources keep /api/sources root)
@router.get("/sources/feeds", response_model=list)
def alias_feeds(db: Session = Depends(get_db), _u: User = Depends(get_current_user)):
    return list_sources(db, _u)

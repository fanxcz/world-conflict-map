from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import require_editor
from app.database import get_db
from app.models import Event, EventSource, Source, User
from app.schemas import EventCreate, EventUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/events", tags=["events"])


def _to_out(e: Event) -> dict:
    sources = []
    for rel in e.sources_rel or []:
        s = rel.source
        sources.append(
            {
                "id": s.id,
                "title": s.title,
                "publisher": s.publisher,
                "url": s.url,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "accessed_at": s.accessed_at.isoformat() if s.accessed_at else None,
                "reliability_note": s.reliability_note,
            }
        )
    return {
        "id": e.id,
        "conflict_id": e.conflict_id,
        "type": e.type,
        "title": e.title,
        "description": e.description,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "event_time": e.event_time.isoformat() if e.event_time else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        "confidence": e.confidence,
        "is_sample": e.is_sample,
        "sources": sources,
    }


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00").replace("+00:00", ""))
    except Exception:
        raise HTTPException(status_code=400, detail=f"bad datetime: {v}")


@router.get("", response_model=dict)
def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    conflict_id: int | None = None,
    type: str | None = Query(default=None, alias="event_type"),
    confidence: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    bbox: str | None = None,
    source: int | None = None,
    sort_by: str = "event_time",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if conflict_id is not None:
        q = q.filter(Event.conflict_id == conflict_id)
    if type:
        q = q.filter(Event.type == type)
    if confidence:
        q = q.filter(Event.confidence == confidence)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Event.title.ilike(like), Event.description.ilike(like)))
    df, dt = _parse_dt(date_from), _parse_dt(date_to)
    if df:
        q = q.filter(Event.event_time >= df)
    if dt:
        q = q.filter(Event.event_time <= dt)
    if bbox:
        try:
            minlon, minlat, maxlon, maxlat = [float(x) for x in bbox.split(",")]
            q = q.filter(
                Event.longitude >= minlon, Event.longitude <= maxlon, Event.latitude >= minlat, Event.latitude <= maxlat
            )
        except Exception:
            raise HTTPException(status_code=400, detail="bbox must be minLon,minLat,maxLon,maxLat")
    if source is not None:
        q = q.join(EventSource, EventSource.event_id == Event.id).filter(EventSource.source_id == source)
    total = q.count()
    col = getattr(Event, sort_by, Event.event_time)
    col = col.desc() if sort_order == "desc" else col.asc()
    items = q.order_by(col).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_to_out(e) for e in items], "total": total, "page": page, "page_size": page_size}


@router.get("/{event_id}", response_model=dict)
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.query(Event).filter(Event.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return _to_out(e)


@router.post("", response_model=dict, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    e = Event(
        conflict_id=payload.conflict_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        latitude=payload.latitude,
        longitude=payload.longitude,
        event_time=payload.event_time,
        confidence=payload.confidence,
    )
    db.add(e)
    db.flush()
    for sid in payload.source_ids:
        if not db.query(Source).filter(Source.id == sid).first():
            db.rollback()
            raise HTTPException(status_code=400, detail=f"source {sid} not found")
        db.add(EventSource(event_id=e.id, source_id=sid))
    write_audit(db, user, "CREATE", "EVENT", e.id, None, {"title": e.title})
    db.commit()
    db.refresh(e)
    return _to_out(e)


@router.put("/{event_id}", response_model=dict)
def update_event(
    event_id: int, payload: EventUpdate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    e = db.query(Event).filter(Event.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    old = {"title": e.title, "type": e.type}
    data = payload.model_dump(exclude_unset=True, exclude={"source_ids"})
    for k, v in data.items():
        setattr(e, k, v)
    if payload.source_ids is not None:
        db.query(EventSource).filter(EventSource.event_id == e.id).delete()
        for sid in payload.source_ids:
            db.add(EventSource(event_id=e.id, source_id=sid))
    write_audit(db, user, "UPDATE", "EVENT", e.id, old, {"title": e.title})
    db.commit()
    db.refresh(e)
    return _to_out(e)


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    e = db.query(Event).filter(Event.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    write_audit(db, user, "DELETE", "EVENT", e.id, {"title": e.title}, None)
    db.delete(e)
    db.commit()

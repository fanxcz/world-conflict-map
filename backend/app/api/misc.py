from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_editor
from app.database import get_db
from app.models import AuditLog, Country, Region, Source, User
from app.schemas import SourceCreate, SourceUpdate
from app.services.audit import write_audit

router_misc = APIRouter(tags=["misc"])


@router_misc.get("/sources", response_model=dict)
def list_sources(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    q = db.query(Source)
    total = q.count()
    items = q.order_by(Source.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "publisher": s.publisher,
                "url": s.url,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "accessed_at": s.accessed_at.isoformat() if s.accessed_at else None,
                "reliability_note": s.reliability_note,
            }
            for s in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router_misc.post("/sources", response_model=dict, status_code=201)
def create_source(payload: SourceCreate, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    s = Source(
        title=payload.title,
        publisher=payload.publisher,
        url=payload.url,
        published_at=payload.published_at,
        reliability_note=payload.reliability_note,
    )
    db.add(s)
    db.flush()
    write_audit(db, user, "CREATE", "SOURCE", s.id, None, {"title": s.title})
    db.commit()
    db.refresh(s)
    return {
        "id": s.id,
        "title": s.title,
        "publisher": s.publisher,
        "url": s.url,
        "published_at": s.published_at.isoformat() if s.published_at else None,
        "accessed_at": s.accessed_at.isoformat(),
        "reliability_note": s.reliability_note,
    }


@router_misc.put("/sources/{source_id}", response_model=dict)
def update_source(
    source_id: int, payload: SourceUpdate, db: Session = Depends(get_db), user: User = Depends(require_editor)
):
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    old = {"title": s.title}
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    write_audit(db, user, "UPDATE", "SOURCE", s.id, old, {"title": s.title})
    db.commit()
    db.refresh(s)
    return {"id": s.id, "title": s.title}


@router_misc.get("/regions", response_model=list)
def list_regions(db: Session = Depends(get_db)):
    return [
        {"id": r.id, "name": r.name, "slug": r.slug, "description": r.description}
        for r in db.query(Region).order_by(Region.name).all()
    ]


@router_misc.get("/countries", response_model=dict)
def list_countries(
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Country)
    if search:
        q = q.filter(Country.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.order_by(Country.name).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "capital": c.capital,
                "lat": c.lat,
                "lon": c.lon,
                "iso2": c.iso2,
                "iso3": c.iso3,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router_misc.get("/audit-logs", response_model=dict)
def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": a.id,
                "user": a.user,
                "action": a.action,
                "object_type": a.object_type,
                "object_id": a.object_id,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "old_value": a.old_value,
                "new_value": a.new_value,
            }
            for a in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router_misc.get("/health", response_model=dict)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok", "version": "1.0.0", "db": "ok" if db_ok else "error"}

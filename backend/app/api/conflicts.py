from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import require_editor
from app.database import get_db
from app.models import Conflict, ConflictSource, Source, User
from app.schemas import ConflictCreate, ConflictOut, ConflictUpdate, SourceOut
from app.schemas.schemas import slugify
from app.services.audit import write_audit

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


def _to_out(c: Conflict) -> ConflictOut:
    sources = [SourceOut.model_validate(s.source) for s in (c.sources_rel or [])]
    return ConflictOut(
        id=c.id,
        name=c.name,
        slug=c.slug,
        region=c.region,
        description=c.description,
        status=c.status,
        start_date=c.start_date,
        end_date=c.end_date,
        last_updated=c.last_updated,
        geometry=c.geometry,
        geometry_type=c.geometry_type,
        is_sample=c.is_sample,
        sources=sources,
    )


@router.get("", response_model=dict)
def list_conflicts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    region: str | None = None,
    status: str | None = None,
    search: str | None = None,
    sort_by: str = Query("last_updated"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    q = db.query(Conflict)
    if region:
        q = q.filter(Conflict.region == region)
    if status:
        q = q.filter(Conflict.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Conflict.name.ilike(like), Conflict.description.ilike(like)))
    total = q.count()
    col = getattr(Conflict, sort_by, Conflict.last_updated)
    col = col.desc() if sort_order == "desc" else col.asc()
    items = q.order_by(col).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_to_out(c).model_dump(mode="json") for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{conflict_id}", response_model=dict)
def get_conflict(conflict_id: int, db: Session = Depends(get_db)):
    c = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return _to_out(c).model_dump(mode="json")


@router.post("", response_model=dict, status_code=201)
def create_conflict(
    payload: ConflictCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    slug = payload.slug or slugify(payload.name)
    if db.query(Conflict).filter(Conflict.slug == slug).first():
        raise HTTPException(status_code=400, detail="slug already exists")
    c = Conflict(
        name=payload.name,
        slug=slug,
        region=payload.region,
        description=payload.description,
        status=payload.status,
        start_date=payload.start_date,
        end_date=payload.end_date,
        geometry=payload.geometry,
        geometry_type=payload.geometry_type,
    )
    db.add(c)
    db.flush()
    for sid in payload.source_ids:
        src = db.query(Source).filter(Source.id == sid).first()
        if not src:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"source {sid} not found")
        db.add(ConflictSource(conflict_id=c.id, source_id=sid))
    write_audit(db, user, "CREATE", "CONFLICT", c.id, None, {"name": c.name, "slug": slug})
    db.commit()
    db.refresh(c)
    return _to_out(c).model_dump(mode="json")


@router.put("/{conflict_id}", response_model=dict)
def update_conflict(
    conflict_id: int,
    payload: ConflictUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    c = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conflict not found")
    old = {"name": c.name, "status": c.status, "region": c.region}
    data = payload.model_dump(exclude_unset=True, exclude={"source_ids"})
    for k, v in data.items():
        setattr(c, k, v)
    if payload.source_ids is not None:
        db.query(ConflictSource).filter(ConflictSource.conflict_id == c.id).delete()
        for sid in payload.source_ids:
            db.add(ConflictSource(conflict_id=c.id, source_id=sid))
    write_audit(db, user, "UPDATE", "CONFLICT", c.id, old, {"name": c.name, "status": c.status})
    db.commit()
    db.refresh(c)
    return _to_out(c).model_dump(mode="json")


@router.delete("/{conflict_id}", status_code=204)
def delete_conflict(
    conflict_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    c = db.query(Conflict).filter(Conflict.id == conflict_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conflict not found")
    write_audit(db, user, "DELETE", "CONFLICT", c.id, {"name": c.name}, None)
    db.delete(c)
    db.commit()

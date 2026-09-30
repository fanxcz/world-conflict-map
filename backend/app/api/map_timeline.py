from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_editor
from app.database import get_db
from app.gis.validation import validate_geometry
from app.models import Event, MapFeature, User
from app.services.audit import write_audit

router = APIRouter(tags=["map"])


@router.get("/map/geojson", response_model=dict)
def map_geojson(
    layer: str | None = None,
    bbox: str | None = None,
    date: str | None = None,
    conflict_id: int | None = None,
    db: Session = Depends(get_db),
):
    features: list[dict] = []
    # map_features
    q = db.query(MapFeature)
    if layer:
        q = q.filter(MapFeature.layer == layer)
    if conflict_id is not None:
        q = q.filter(MapFeature.conflict_id == conflict_id)
    for mf in q.limit(2000).all():
        geom = mf.geometry or {}
        coords = geom.get("coordinates")
        if bbox and geom.get("type") == "Point" and coords and len(coords) == 2:
            try:
                minlon, minlat, maxlon, maxlat = [float(x) for x in bbox.split(",")]
                lon, lat = coords
                if not (minlon <= lon <= maxlon and minlat <= lat <= maxlat):
                    continue
            except Exception:
                pass
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "kind": "map_feature",
                    "id": mf.id,
                    "name": mf.name,
                    "feature_type": mf.feature_type,
                    "layer": mf.layer,
                    "color": mf.color,
                    "conflict_id": mf.conflict_id,
                    **(mf.properties or {}),
                },
            }
        )
    # events as points (respect date filter for timeline)
    eq = db.query(Event)
    if date:
        try:
            d = datetime.fromisoformat(date)
            eq = eq.filter(Event.event_time <= d)
        except Exception:
            raise HTTPException(status_code=400, detail="bad date, use YYYY-MM-DD")
    if bbox:
        try:
            minlon, minlat, maxlon, maxlat = [float(x) for x in bbox.split(",")]
            eq = eq.filter(
                Event.longitude >= minlon, Event.longitude <= maxlon, Event.latitude >= minlat, Event.latitude <= maxlat
            )
        except Exception:
            raise HTTPException(status_code=400, detail="bad bbox")
    if conflict_id is not None:
        eq = eq.filter(Event.conflict_id == conflict_id)
    for e in eq.limit(2000).all():
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e.longitude, e.latitude]},
                "properties": {
                    "kind": "event",
                    "id": e.id,
                    "type": e.type,
                    "title": e.title,
                    "confidence": e.confidence,
                    "event_time": e.event_time.isoformat() if e.event_time else None,
                    "conflict_id": e.conflict_id,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/timeline", response_model=dict)
def timeline(date: str | None = None, conflict_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Event)
    if conflict_id is not None:
        q = q.filter(Event.conflict_id == conflict_id)
    if date:
        try:
            d = datetime.fromisoformat(date)
            q = q.filter(Event.event_time <= d)
        except Exception:
            raise HTTPException(status_code=400, detail="bad date")
    total = q.count()
    by_type = dict(q.with_entities(Event.type, func.count(Event.id)).group_by(Event.type).all())
    by_conf = dict(q.with_entities(Event.confidence, func.count(Event.id)).group_by(Event.confidence).all())
    latest = q.order_by(Event.event_time.desc()).limit(10).all()
    return {
        "date": date,
        "total_events": total,
        "by_type": by_type,
        "by_confidence": by_conf,
        "latest": [
            {"id": e.id, "title": e.title, "type": e.type, "event_time": e.event_time.isoformat()} for e in latest
        ],
    }


@router.get("/map/features", response_model=dict)
def list_features(
    layer: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(MapFeature)
    if layer:
        q = q.filter(MapFeature.layer == layer)
    total = q.count()
    items = q.order_by(MapFeature.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "feature_type": m.feature_type,
                "layer": m.layer,
                "color": m.color,
                "geometry": m.geometry,
                "properties": m.properties,
                "conflict_id": m.conflict_id,
            }
            for m in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/map/features", response_model=dict, status_code=201)
def create_feature(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    geom = payload.get("geometry")
    if not geom:
        raise HTTPException(status_code=400, detail="geometry required")
    ok, msg = validate_geometry(geom)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    mf = MapFeature(
        name=payload.get("name"),
        description=payload.get("description"),
        feature_type=payload.get("feature_type", "important_location"),
        layer=payload.get("layer", "conflict_zones"),
        color=payload.get("color", "#ff5252"),
        geometry=geom,
        properties=payload.get("properties"),
        conflict_id=payload.get("conflict_id"),
    )
    db.add(mf)
    db.flush()
    write_audit(db, user, "CREATE", "MAP_FEATURE", mf.id, None, {"name": mf.name})
    db.commit()
    db.refresh(mf)
    return {"id": mf.id, "name": mf.name}


@router.put("/map/features/{fid}", response_model=dict)
def update_feature(fid: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    mf = db.query(MapFeature).filter(MapFeature.id == fid).first()
    if not mf:
        raise HTTPException(status_code=404, detail="Feature not found")
    if "geometry" in payload and payload["geometry"] is not None:
        ok, msg = validate_geometry(payload["geometry"])
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
    old = {"name": mf.name}
    for k in ("name", "description", "feature_type", "layer", "color", "geometry", "properties", "conflict_id"):
        if k in payload:
            setattr(mf, k, payload[k])
    write_audit(db, user, "UPDATE", "MAP_FEATURE", mf.id, old, {"name": mf.name})
    db.commit()
    return {"id": mf.id, "name": mf.name}


@router.delete("/map/features/{fid}", status_code=204)
def delete_feature(fid: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    mf = db.query(MapFeature).filter(MapFeature.id == fid).first()
    if not mf:
        raise HTTPException(status_code=404, detail="Feature not found")
    write_audit(db, user, "DELETE", "MAP_FEATURE", mf.id, {"name": mf.name}, None)
    db.delete(mf)
    db.commit()

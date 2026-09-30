"""GeoJSON importer: python -m app.import_geojson file.geojson [--conflict-id N] [--layer conflict_zones]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.database import SessionLocal, init_db
from app.gis.validation import validate_feature, validate_feature_collection
from app.models import MapFeature


def import_file(path: str, conflict_id: int | None = None, layer: str = "conflict_zones") -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"invalid JSON: {exc}"}
    feats: list[dict] = []
    if data.get("type") == "FeatureCollection":
        ok, msg, feats = validate_feature_collection(data)
        if not ok:
            return {"ok": False, "error": msg}
    elif data.get("type") == "Feature":
        ok, msg = validate_feature(data)
        if not ok:
            return {"ok": False, "error": msg}
        feats = [data]
    else:
        geom = data.get("geometry", data) if isinstance(data, dict) else None
        from app.gis.validation import validate_geometry

        ok, msg = validate_geometry(geom if isinstance(geom, dict) else {})
        if not ok:
            return {"ok": False, "error": f"unsupported GeoJSON root (want FeatureCollection/Feature): {msg}"}
        feats = [{"type": "Feature", "geometry": geom, "properties": data.get("properties", {})}]
    init_db()
    db = SessionLocal()
    created = 0
    try:
        for f in feats:
            props = f.get("properties") or {}
            mf = MapFeature(
                name=props.get("name") or props.get("title"),
                description=props.get("description"),
                feature_type=props.get("feature_type", props.get("type", "important_location")),
                layer=props.get("layer", layer),
                color=props.get("color", "#ff5252"),
                geometry=f["geometry"],
                properties=props,
                conflict_id=conflict_id,
            )
            db.add(mf)
            created += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()
    return {"ok": True, "imported": created}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    conflict_id = None
    layer = "conflict_zones"
    for i, a in enumerate(argv):
        if a == "--conflict-id" and i + 1 < len(argv):
            conflict_id = int(argv[i + 1])
        if a == "--layer" and i + 1 < len(argv):
            layer = argv[i + 1]
    res = import_file(path, conflict_id, layer)
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

from __future__ import annotations

from shapely.geometry import shape

ALLOWED = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


def validate_geometry(geom: dict) -> tuple[bool, str]:
    if not isinstance(geom, dict):
        return False, "geometry must be an object"
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype not in ALLOWED:
        return False, f"unsupported geometry type: {gtype}"
    if coords is None:
        return False, "missing coordinates"
    try:
        s = shape(geom)
        if s.is_empty:
            return False, "empty geometry"
        if not s.is_valid:
            return False, "invalid geometry (self-intersection?)"
        # longitude/latitude sanity for Point-ish; polygons checked via bounds
        b = s.bounds  # minx, miny, maxx, maxy
        if b[0] < -180 or b[2] > 180 or b[1] < -90 or b[3] > 90:
            return False, "coordinates out of WGS84 bounds"
    except Exception as exc:
        return False, f"unparseable geometry: {exc}"
    return True, "ok"


def validate_feature(feature: dict) -> tuple[bool, str]:
    if not isinstance(feature, dict):
        return False, "feature must be an object"
    if feature.get("type") != "Feature":
        return False, "type must be 'Feature'"
    geom = feature.get("geometry")
    if geom is None:
        return False, "missing geometry"
    return validate_geometry(geom)


def validate_feature_collection(fc: dict) -> tuple[bool, str, list[dict]]:
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
        return False, "root must be FeatureCollection", []
    feats = fc.get("features", [])
    if not isinstance(feats, list):
        return False, "features must be a list", []
    errors = []
    for i, f in enumerate(feats):
        ok, msg = validate_feature(f)
        if not ok:
            errors.append(f"feature[{i}]: {msg}")
    if errors:
        return False, "; ".join(errors[:10]), []
    return True, "ok", feats

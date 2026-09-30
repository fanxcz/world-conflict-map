import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def _seed_users():
    db = TestingSession()
    try:
        if not db.query(User).filter(User.email == "admin@t.t").first():
            db.add(User(email="admin@t.t", hashed_password=hash_password("Admin123!"), role="admin"))
        if not db.query(User).filter(User.email == "viewer@t.t").first():
            db.add(User(email="viewer@t.t", hashed_password=hash_password("Viewer123!"), role="viewer"))
        db.commit()
    finally:
        db.close()


_seed_users()


def override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def token(email: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_h(email: str, password: str) -> dict:
    return {"Authorization": f"Bearer {token(email, password)}"}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_and_permissions():
    h_admin = auth_h("admin@t.t", "Admin123!")
    # me
    r = client.get("/api/auth/me", headers=h_admin)
    assert r.status_code == 200
    # viewer cannot create
    h_view = auth_h("viewer@t.t", "Viewer123!")
    r = client.post("/api/conflicts", json={"name": "X", "region": "Europe"}, headers=h_view)
    assert r.status_code == 403
    # unauthenticated cannot create
    r = client.post("/api/conflicts", json={"name": "X"})
    assert r.status_code == 401


def test_conflict_crud_and_filtering():
    h = auth_h("admin@t.t", "Admin123!")
    r = client.post(
        "/api/conflicts",
        json={
            "name": "Test Conflict Alpha",
            "region": "Europe",
            "status": "active",
            "description": "unit test",
            "geometry": {"type": "Point", "coordinates": [10, 50]},
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # get
    assert client.get(f"/api/conflicts/{cid}").status_code == 200
    # filter by region
    r = client.get("/api/conflicts?region=Europe")
    assert r.json()["total"] >= 1
    # update
    r = client.put(f"/api/conflicts/{cid}", json={"status": "historical"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "historical"
    # bad status rejected
    r = client.post("/api/conflicts", json={"name": "Bad", "status": "nope"}, headers=h)
    assert r.status_code == 422
    # delete
    assert client.delete(f"/api/conflicts/{cid}", headers=h).status_code == 204


def test_sources_and_events():
    h = auth_h("admin@t.t", "Admin123!")
    s = client.post(
        "/api/sources", json={"title": "Unit Source", "publisher": "U", "url": "https://example.com"}, headers=h
    )
    assert s.status_code == 201, s.text
    sid = s.json()["id"]
    c = client.post("/api/conflicts", json={"name": "Ev Conflict", "region": "Asia"}, headers=h).json()
    e = client.post(
        "/api/events",
        json={
            "conflict_id": c["id"],
            "type": "clash",
            "title": "Unit clash",
            "latitude": 10.0,
            "longitude": 20.0,
            "event_time": "2026-09-01T10:00:00",
            "confidence": "CONFIRMED",
            "source_ids": [sid],
        },
        headers=h,
    )
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    # every event must expose sources
    g = client.get(f"/api/events/{eid}").json()
    assert len(g["sources"]) == 1
    # bbox filter includes, far bbox excludes
    assert client.get("/api/events?bbox=19,9,21,11").json()["total"] >= 1
    assert client.get("/api/events?bbox=0,0,1,1").json()["total"] == 0
    # confidence filter
    assert client.get("/api/events?confidence=CONFIRMED").json()["total"] >= 1
    # pagination shape
    r = client.get("/api/events?page=1&page_size=5")
    assert set(("items", "total", "page", "page_size")) <= set(r.json().keys())


def test_geojson_validation_and_map():
    h = auth_h("admin@t.t", "Admin123!")
    bad = client.post("/api/map/features", json={"geometry": {"type": "Point", "coordinates": [999, 999]}}, headers=h)
    assert bad.status_code == 400
    good = client.post(
        "/api/map/features",
        json={
            "name": "Unit polygon",
            "feature_type": "conflict_zone",
            "layer": "conflict_zones",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        },
        headers=h,
    )
    assert good.status_code == 201, good.text
    r = client.get("/api/map/geojson")
    assert r.status_code == 200
    assert r.json()["type"] == "FeatureCollection"
    assert len(r.json()["features"]) >= 1
    # timeline
    t = client.get("/api/timeline")
    assert t.status_code == 200 and "total_events" in t.json()


def test_audit_log_and_sql_injection():
    h = auth_h("admin@t.t", "Admin123!")
    # audit visible to admin
    r = client.get("/api/audit-logs", headers=h)
    assert r.status_code == 200 and r.json()["total"] >= 1
    # viewer forbidden from audit
    hv = auth_h("viewer@t.t", "Viewer123!")
    assert client.get("/api/audit-logs", headers=hv).status_code == 403
    # SQL injection attempt must not break (parameterized queries)
    r = client.get("/api/conflicts?search=' OR '1'='1")
    assert r.status_code == 200
    r = client.post("/api/auth/login", json={"email": "' OR 1=1 --", "password": "x"})
    assert r.status_code in (401, 422)

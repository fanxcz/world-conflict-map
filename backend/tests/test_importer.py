"""Importer pipeline tests: adapters, moderation, dedup, dashboard.

Uses shared in-memory app from test_api (dependency-overridden get_db).
Demo feeds are local files (DEMO SOURCE, fictional).
"""

from pathlib import Path

from app.importer.adapters import ADAPTERS
from tests.test_api import auth_h, client

SAMPLE = Path(__file__).resolve().parent.parent.parent / "data" / "sample"
ADMIN = auth_h("admin@t.t", "Admin123!")
VIEWER = auth_h("viewer@t.t", "Viewer123!")


def _mk(name: str, stype: str, fname: str, cfg: dict | None = None) -> int:
    r = client.post(
        "/api/data-sources",
        json={
            "name": name,
            "url": f"local:{SAMPLE / fname}",
            "source_type": stype,
            "update_interval": "manual",
            "fetch_config": cfg or {},
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_adapters_parse_demo_files():
    rss_raw, _ = ADAPTERS["rss"].fetch(f"local:{SAMPLE / 'demo_rss.xml'}", {})
    assert len(ADAPTERS["rss"].parse(rss_raw, {})) == 3
    j_raw, _ = ADAPTERS["json_api"].fetch(f"local:{SAMPLE / 'demo_api.json'}", {})
    assert len(ADAPTERS["json_api"].parse(j_raw, {})) == 3
    g_raw, _ = ADAPTERS["geojson"].fetch(f"local:{SAMPLE / 'demo.geojson'}", {})
    assert len(ADAPTERS["geojson"].parse(g_raw, {})) == 2
    c_raw, _ = ADAPTERS["csv"].fetch(f"local:{SAMPLE / 'demo.csv'}", {})
    assert len(ADAPTERS["csv"].parse(c_raw, {})) == 2
    # no coords invented for RSS: lat/lon must be None
    nev = ADAPTERS["rss"].normalize(ADAPTERS["rss"].parse(rss_raw, {})[0], {})
    assert nev.latitude is None and nev.longitude is None
    ok, _ = ADAPTERS["rss"].validate(nev)
    assert ok


def test_source_crud_and_test_and_secrets_masked():
    sid = _mk("UT RSS", "rss", "demo_rss.xml", {"headers": {"Authorization": "Bearer s3cret"}})
    r = client.get(f"/api/data-sources/{sid}", headers=ADMIN)
    assert r.json()["fetch_config"]["headers"]["Authorization"] == "***"
    t = client.post(f"/api/data-sources/{sid}/test", headers=ADMIN)
    assert t.status_code == 200, t.text
    assert t.json()["connection"] == "OK" and t.json()["items"] == 3
    # bad url -> FAIL, never raises 500
    bad = _mk("UT BAD", "rss", "demo_rss.xml")
    client.put(f"/api/data-sources/{bad}", json={"url": "https://127.0.0.1:9/nope"}, headers=ADMIN)
    t2 = client.post(f"/api/data-sources/{bad}/test", headers=ADMIN)
    assert t2.json()["connection"] == "FAIL"
    # enable/disable
    assert client.post(f"/api/data-sources/{sid}/disable", headers=ADMIN).json()["status"] == "DISABLED"
    assert client.post(f"/api/data-sources/{sid}/enable", headers=ADMIN).json()["enabled"] is True


def test_full_pipeline_pending_approve_public():
    sid = _mk("UT JSON", "json_api", "demo_api.json", {"mapping": {}})
    run = client.post(f"/api/data-sources/{sid}/update", headers=ADMIN).json()
    assert run["fetched"] == 3 and run["new"] >= 1, run
    # pending visible to editor, NOT in public events
    pend = client.get("/api/pending?page_size=100", headers=ADMIN).json()
    assert pend["total"] >= 1
    titles = [p["title"] for p in pend["items"]]
    pub = client.get("/api/events?page_size=200").json()
    for t in titles:
        assert all(t != e["title"] for e in pub["items"]), "PENDING leaked to public API"
    # approve a KNOWN item
    known = next(p for p in pend["items"] if p["location_status"] == "KNOWN" and p["latitude"] is not None)
    ap = client.post(f"/api/pending/{known['id']}/approve", json={}, headers=ADMIN)
    assert ap.status_code == 200, ap.text
    pub2 = client.get("/api/events?page_size=200").json()
    assert any(e["title"] == known["title"] for e in pub2["items"])
    # provenance kept
    det = client.get(f"/api/imports/{known['id']}", headers=ADMIN).json()
    assert det["status"] == "APPROVED" and det["provenance"]["source_name"] == "UT JSON"
    # history exists
    h = client.get(f"/api/events/{ap.json()['event_id']}/history", headers=ADMIN).json()
    assert len(h) >= 1 and h[0]["who"] == "admin@t.t"


def test_location_unknown_blocked_until_fixed():
    sid = _mk("UT RSS2", "rss", "demo_rss.xml")
    client.post(f"/api/data-sources/{sid}/update", headers=ADMIN)
    pend = client.get("/api/pending?page_size=100", headers=ADMIN).json()
    unk = next(p for p in pend["items"] if p["location_status"] == "LOCATION_UNKNOWN")
    r = client.post(f"/api/pending/{unk['id']}/approve", json={}, headers=ADMIN)
    assert r.status_code == 400 and "LOCATION_UNKNOWN" in r.text
    # admin fixes coords via EDIT then approves
    e = client.put(f"/api/pending/{unk['id']}", json={"latitude": 50.0, "longitude": 30.0}, headers=ADMIN)
    assert e.status_code == 200
    # still LOCATION_UNKNOWN flag -> set by fetch; service checks coords now? re-check:
    # our approve checks coords; with coords set it proceeds
    r2 = client.post(f"/api/pending/{unk['id']}/approve", json={}, headers=ADMIN)
    assert r2.status_code == 200, r2.text


def test_dedup_rerun_no_new_and_logs_dashboard():
    sid = _mk("UT GEO", "geojson", "demo.geojson")
    first = client.post(f"/api/data-sources/{sid}/update", headers=ADMIN).json()
    assert first["new"] == 2, first
    second = client.post(f"/api/data-sources/{sid}/update", headers=ADMIN).json()
    assert second["duplicates"] >= 2 and second["new"] == 0, second
    logs = client.get("/api/import-logs?page_size=10", headers=ADMIN).json()
    assert logs["total"] >= 2
    dash = client.get("/api/importer/dashboard", headers=ADMIN).json()
    assert dash["sources"] >= 1 and dash["pending"] >= 1
    fresh = client.get("/api/freshness").json()
    assert "last_updated" in fresh and "stale" in fresh


def test_reject_merge_duplicate_and_permissions():
    sid = _mk("UT CSV", "csv", "demo.csv")
    client.post(f"/api/data-sources/{sid}/update", headers=ADMIN)
    pend = client.get("/api/pending?page_size=100", headers=ADMIN).json()
    assert pend["total"] >= 1
    # viewer cannot touch moderation
    assert client.get("/api/pending", headers=VIEWER).status_code == 403
    # duplicate flow
    known = next(p for p in pend["items"] if p["latitude"] is not None)
    ev_id = client.post(f"/api/pending/{known['id']}/approve", json={}, headers=ADMIN).json()["event_id"]
    other = next(
        p
        for p in client.get("/api/pending?page_size=100", headers=ADMIN).json()["items"]
        if p["id"] != known["id"] and p["status"] == "PENDING"
    )
    d = client.post(f"/api/pending/{other['id']}/duplicate", json={"of_id": ev_id, "kind": "event"}, headers=ADMIN)
    assert d.json()["status"] == "DUPLICATE"
    # multi-source: surviving event now has >=1 source linked
    ev = client.get(f"/api/events/{ev_id}").json()
    assert len(ev["sources"]) >= 1
    # reject flow
    rest = [
        p for p in client.get("/api/pending?page_size=100", headers=ADMIN).json()["items"] if p["status"] == "PENDING"
    ]
    if rest:
        r = client.post(f"/api/pending/{rest[0]['id']}/reject", json={"reason": "test"}, headers=ADMIN)
        assert r.json()["status"] == "REJECTED"
    # audit recorded an approve
    logs = client.get("/api/audit-logs", headers=ADMIN).json()
    assert any("PENDING" in (l.get("object_type", "") or "") for l in logs["items"])

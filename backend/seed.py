"""Seed SAMPLE/Demo data. Idempotent. Usage: python seed.py"""

from __future__ import annotations

from datetime import date, datetime

from app.auth.security import hash_password
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Conflict, ConflictSource, Country, Event, EventSource, MapFeature, Region, Source, User

settings = get_settings()

REGIONS = [
    ("Europe", "europe", "European region"),
    ("Middle East", "middle-east", "Middle East region"),
    ("Africa", "africa", "African region"),
    ("Asia", "asia", "Asian region"),
    ("Americas", "americas", "Americas region"),
    ("Other", "other", "Other regions"),
]

COUNTRIES = [
    ("UA", "UKR", "Ukraine", "Kyiv", 50.45, 30.52, "europe"),
    ("DE", "DEU", "Germany", "Berlin", 52.52, 13.40, "europe"),
    ("SY", "SYR", "Syria", "Damascus", 33.51, 36.29, "middle-east"),
    ("NG", "NGA", "Nigeria", "Abuja", 9.06, 7.48, "africa"),
    ("IN", "IND", "India", "New Delhi", 28.61, 77.20, "asia"),
    ("US", "USA", "United States", "Washington", 38.90, -77.03, "americas"),
    ("BR", "BRA", "Brazil", "Brasilia", -15.79, -47.88, "americas"),
    ("FR", "FRA", "France", "Paris", 48.85, 2.35, "europe"),
]


def run() -> dict:
    init_db()
    db = SessionLocal()
    try:
        # admin
        admin = db.query(User).filter(User.email == settings.admin_email).first()
        if not admin:
            admin = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
        # regions
        slug_to_region = {}
        for name, slug, desc in REGIONS:
            r = db.query(Region).filter(Region.slug == slug).first()
            if not r:
                r = Region(name=name, slug=slug, description=desc)
                db.add(r)
                db.flush()
            slug_to_region[slug] = r
        db.flush()
        # countries
        for iso2, iso3, name, cap, lat, lon, rslug in COUNTRIES:
            if not db.query(Country).filter(Country.name == name).first():
                db.add(
                    Country(
                        iso2=iso2,
                        iso3=iso3,
                        name=name,
                        capital=cap,
                        lat=lat,
                        lon=lon,
                        region_id=slug_to_region[rslug].id,
                    )
                )
        db.flush()
        # sources (clearly sample/documentation sources)
        sample_sources = [
            ("WCM Documentation Sample", "WCM", "https://example.com/sample-1", "Sample publisher note"),
            ("Open Data Sample Feed", "WCM Samples", "https://example.com/sample-2", "Demo only"),
        ]
        src_objs = []
        for title, pub, url, note in sample_sources:
            s = db.query(Source).filter(Source.title == title).first()
            if not s:
                s = Source(title=title, publisher=pub, url=url, reliability_note=note)
                db.add(s)
                db.flush()
            src_objs.append(s)
        # sample conflicts (explicitly fictional SAMPLE)
        samples = [
            {
                "name": "[SAMPLE] Northland Border Monitoring Zone",
                "slug": "sample-northland-zone",
                "region": "Europe",
                "status": "active",
                "start_date": date(2025, 1, 10),
                "description": "DEMO / SAMPLE DATA: fictional monitoring zone for UI testing. Not a real conflict.",
                "lon": 22.0,
                "lat": 52.0,
            },
            {
                "name": "[SAMPLE] Southsea Humanitarian Corridor",
                "slug": "sample-southsea-corridor",
                "region": "Asia",
                "status": "reported",
                "start_date": date(2025, 6, 1),
                "description": "DEMO / SAMPLE DATA: fictional corridor scenario for timeline testing.",
                "lon": 100.0,
                "lat": 8.0,
            },
            {
                "name": "[SAMPLE] Historical Archive Example",
                "slug": "sample-historical-archive",
                "region": "Africa",
                "status": "historical",
                "start_date": date(2024, 3, 1),
                "end_date": date(2024, 9, 1),
                "description": "DEMO / SAMPLE DATA: fictional historical entry.",
                "lon": 20.0,
                "lat": 5.0,
            },
        ]
        for sc in samples:
            c = db.query(Conflict).filter(Conflict.slug == sc["slug"]).first()
            if not c:
                c = Conflict(
                    name=sc["name"],
                    slug=sc["slug"],
                    region=sc["region"],
                    status=sc["status"],
                    start_date=sc["start_date"],
                    end_date=sc.get("end_date"),
                    description=sc["description"],
                    geometry={"type": "Point", "coordinates": [sc["lon"], sc["lat"]]},
                    geometry_type="Point",
                    is_sample=True,
                )
                db.add(c)
                db.flush()
                for s in src_objs:
                    db.add(ConflictSource(conflict_id=c.id, source_id=s.id))
        db.flush()
        # sample events
        c1 = db.query(Conflict).filter(Conflict.slug == "sample-northland-zone").first()
        if c1 and db.query(Event).filter(Event.conflict_id == c1.id).count() == 0:
            evts = [
                (
                    "humanitarian",
                    "[SAMPLE] Aid convoy reached checkpoint",
                    52.05,
                    22.1,
                    datetime(2026, 9, 20, 10, 0),
                    "REPORTED",
                ),
                (
                    "ceasefire",
                    "[SAMPLE] Local pause in activity reported",
                    51.95,
                    21.9,
                    datetime(2026, 9, 25, 12, 0),
                    "UNVERIFIED",
                ),
                (
                    "diplomatic",
                    "[SAMPLE] Statement issued by observers",
                    52.0,
                    22.0,
                    datetime(2026, 9, 28, 9, 0),
                    "CONFIRMED",
                ),
                ("clash", "[SAMPLE] Minor incident (fictional)", 52.1, 22.2, datetime(2026, 9, 29, 15, 30), "REPORTED"),
            ]
            for etype, title, lat, lon, dt, conf in evts:
                e = Event(
                    conflict_id=c1.id,
                    type=etype,
                    title=title,
                    description="DEMO / SAMPLE DATA: fictional event for testing.",
                    latitude=lat,
                    longitude=lon,
                    event_time=dt,
                    confidence=conf,
                    is_sample=True,
                )
                db.add(e)
                db.flush()
                db.add(EventSource(event_id=e.id, source_id=src_objs[0].id))
        db.flush()
        # sample map features
        if db.query(MapFeature).count() == 0:
            db.add(
                MapFeature(
                    name="[SAMPLE] Monitoring perimeter",
                    description="DEMO / SAMPLE DATA",
                    feature_type="conflict_zone",
                    layer="conflict_zones",
                    color="#ff5252",
                    geometry={
                        "type": "Polygon",
                        "coordinates": [[[21.5, 51.7], [22.5, 51.7], [22.5, 52.3], [21.5, 52.3], [21.5, 51.7]]],
                    },
                    properties={"sample": True},
                    is_sample=True,
                )
            )
            db.add(
                MapFeature(
                    name="[SAMPLE] Observation line",
                    description="DEMO / SAMPLE DATA",
                    feature_type="frontline",
                    layer="frontlines",
                    color="#ffb300",
                    geometry={"type": "LineString", "coordinates": [[21.8, 51.9], [22.0, 52.0], [22.2, 52.05]]},
                    properties={"sample": True},
                    is_sample=True,
                )
            )
            db.add(
                MapFeature(
                    name="[SAMPLE] Supply route",
                    description="DEMO / SAMPLE DATA",
                    feature_type="movement",
                    layer="movements",
                    color="#40c4ff",
                    geometry={"type": "LineString", "coordinates": [[22.0, 52.0], [22.3, 52.1]]},
                    properties={"sample": True},
                    is_sample=True,
                )
            )
        # DEMO feed sources (local files, explicitly fictional, disabled auto-approve)
        from pathlib import Path

        from app.models import DataSource
        demo_dir = Path(__file__).resolve().parent.parent / "data" / "sample"
        demo_feeds = [
            ("[DEMO SOURCE] Sample Relief RSS (fictional)", "rss", "demo_rss.xml", "manual"),
            ("[DEMO SOURCE] Sample JSON API (fictional)", "json_api", "demo_api.json", "manual"),
            ("[DEMO SOURCE] Sample GeoJSON (fictional)", "geojson", "demo.geojson", "manual"),
            ("[DEMO SOURCE] Sample CSV (fictional)", "csv", "demo.csv", "manual"),
        ]
        for name, stype, fname, interval in demo_feeds:
            if not db.query(DataSource).filter(DataSource.name == name).first():
                db.add(DataSource(
                    name=name, publisher="WCM Demo", url=f"local:{demo_dir / fname}",
                    source_type=stype, enabled=True, auto_approve=False,
                    trust_level="LOW", update_interval=interval, status="NEVER_RUN",
                    fetch_config={"mapping": {}} if stype in ("json_api", "csv") else None,
                    is_demo=True,
                ))
        db.commit()
    finally:
        db.close()
    return {"ok": True, "admin": settings.admin_email}


if __name__ == "__main__":
    print(run())

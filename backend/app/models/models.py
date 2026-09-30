from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)  # admin|editor|viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Country(Base):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iso2: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    iso3: Mapped[str | None] = mapped_column(String(3), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    capital: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id", ondelete="SET NULL"), nullable=True)
    region: Mapped[Region | None] = relationship("Region", lazy="joined")

    __table_args__ = (Index("ix_countries_name_lower", "name"),)


class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(120), default="Other", nullable=False, index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active|historical|reported
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    sources_rel: Mapped[list[ConflictSource]] = relationship(
        "ConflictSource", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="conflict", cascade="all, delete-orphan", lazy="selectin"
    )

    # NOTE (PostGIS production): when DATABASE_URL is postgresql+psycopg2 with PostGIS,
    # migration `alembic/versions/0002_postgis.py` adds:
    #   ALTER TABLE conflicts ADD COLUMN geom geometry(Geometry,4326);
    #   CREATE INDEX ix_conflicts_geom ON conflicts USING GIST (geom);
    # Portable JSON `geometry` column is always the source of truth for API.


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(20), default="REPORTED", nullable=False, index=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    conflict: Mapped[Conflict | None] = relationship("Conflict", back_populates="events", lazy="joined")
    sources_rel: Mapped[list[EventSource]] = relationship("EventSource", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_events_lat_lon", "latitude", "longitude"),
        Index("ix_events_time_conf", "event_time", "confidence"),
    )


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reliability_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventSource(Base):
    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[Source] = relationship("Source", lazy="joined")
    __table_args__ = (UniqueConstraint("event_id", "source_id", name="uq_event_source"),)


class ConflictSource(Base):
    __tablename__ = "conflict_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conflict_id: Mapped[int] = mapped_column(ForeignKey("conflicts.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[Source] = relationship("Source", lazy="joined")
    __table_args__ = (UniqueConstraint("conflict_id", "source_id", name="uq_conflict_source"),)


class MapFeature(Base):
    __tablename__ = "map_features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(60), default="conflict_zones", nullable=False, index=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # CREATE|UPDATE|DELETE
    object_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# External data-source import pipeline (moderated).
# Public map serves ONLY approved rows from events/map_features.
# Everything fetched from outside lands in raw_imports/pending_items first.
# ---------------------------------------------------------------------------

SOURCE_TYPES = ("rss", "atom", "json_api", "geojson", "csv", "xml")
TRUST_LEVELS = ("UNKNOWN", "LOW", "MEDIUM", "HIGH")
SOURCE_STATUS = ("ACTIVE", "DISABLED", "ERROR", "NEVER_RUN")
INTERVALS = {
    "manual": 0,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "6h": 21600,
    "daily": 86400,
}
PENDING_STATUS = ("PENDING", "APPROVED", "REJECTED", "DUPLICATE", "MERGED")


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trust_level: Mapped[str] = mapped_column(String(10), default="UNKNOWN", nullable=False)
    update_interval: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="NEVER_RUN", nullable=False, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_approved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetch_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class RawImport(Base):
    __tablename__ = "raw_imports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PendingItem(Base):
    __tablename__ = "pending_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    raw_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_imports.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), default="clash", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    location_status: Mapped[str] = mapped_column(String(20), default="KNOWN", nullable=False)  # KNOWN|LOCATION_UNKNOWN
    event_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="REPORTED", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflicts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False, index=True)
    duplicate_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    candidate_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duplicate_of_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class PendingItemHistory(Base):
    __tablename__ = "pending_item_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pending_id: Mapped[int] = mapped_column(ForeignKey("pending_items.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    who: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ImportLog(Base):
    __tablename__ = "import_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="SUCCESS", nullable=False, index=True)
    fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventHistory(Base):
    __tablename__ = "event_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    who: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

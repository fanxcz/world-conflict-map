from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

EVENT_TYPES = {
    "clash",
    "airstrike",
    "artillery",
    "explosion",
    "infrastructure_damage",
    "territorial_change",
    "military_movement",
    "ceasefire",
    "diplomatic",
    "humanitarian",
}
CONFIDENCE = {"CONFIRMED", "REPORTED", "UNVERIFIED"}
CONFLICT_STATUS = {"active", "historical", "reported"}
GEOM_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


def slugify(value: str) -> str:
    import re

    v = value.strip().lower()
    v = re.sub(r"[^a-z0-9]+", "-", v).strip("-")
    return v or "item"


# ---------- Auth ----------
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or len(v) < 3:
            raise ValueError("invalid email")
        return v


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Sources ----------
class SourceBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    published_at: datetime | None = None
    reliability_note: str | None = None


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    publisher: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    published_at: datetime | None = None
    reliability_note: str | None = None


class SourceOut(SourceBase):
    id: int
    accessed_at: datetime

    class Config:
        from_attributes = True


# ---------- Conflicts ----------
class ConflictBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    region: str = Field(default="Other", max_length=120)
    description: str | None = None
    status: str = Field(default="active")
    start_date: date | None = None
    end_date: date | None = None
    geometry: dict | None = None
    geometry_type: str | None = None

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in CONFLICT_STATUS:
            raise ValueError(f"status must be one of {sorted(CONFLICT_STATUS)}")
        return v

    @field_validator("geometry")
    @classmethod
    def check_geometry(cls, v: Any) -> Any:
        if v is None:
            return v
        if not isinstance(v, dict) or v.get("type") not in GEOM_TYPES or "coordinates" not in v:
            raise ValueError("geometry must be GeoJSON geometry with type+coordinates")
        return v


class ConflictCreate(ConflictBase):
    slug: str | None = None
    source_ids: list[int] = Field(default_factory=list)


class ConflictUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    geometry: dict | None = None
    geometry_type: str | None = None
    source_ids: list[int] | None = None

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in CONFLICT_STATUS:
            raise ValueError(f"status must be one of {sorted(CONFLICT_STATUS)}")
        return v


class ConflictOut(BaseModel):
    id: int
    name: str
    slug: str
    region: str
    description: str | None
    status: str
    start_date: date | None
    end_date: date | None
    last_updated: datetime
    geometry: dict | None
    geometry_type: str | None
    is_sample: bool
    sources: list[SourceOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------- Events ----------
class EventBase(BaseModel):
    conflict_id: int | None = None
    type: str
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    event_time: datetime
    confidence: str = Field(default="REPORTED")

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"type must be one of {sorted(EVENT_TYPES)}")
        return v

    @field_validator("confidence")
    @classmethod
    def check_conf(cls, v: str) -> str:
        if v not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE)}")
        return v


class EventCreate(EventBase):
    source_ids: list[int] = Field(default_factory=list)


class EventUpdate(BaseModel):
    conflict_id: int | None = None
    type: str | None = None
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    event_time: datetime | None = None
    confidence: str | None = None
    source_ids: list[int] | None = None


class EventOut(BaseModel):
    id: int
    conflict_id: int | None
    type: str
    title: str
    description: str | None
    latitude: float
    longitude: float
    event_time: datetime
    created_at: datetime
    updated_at: datetime
    confidence: str
    is_sample: bool
    sources: list[SourceOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ---------- Regions / Countries ----------
class RegionOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None

    class Config:
        from_attributes = True


class CountryOut(BaseModel):
    id: int
    name: str
    capital: str | None
    lat: float | None
    lon: float | None
    iso2: str | None
    iso3: str | None

    class Config:
        from_attributes = True


# ---------- Map features ----------
class MapFeatureCreate(BaseModel):
    name: str | None = None
    description: str | None = None
    feature_type: str
    layer: str = "conflict_zones"
    color: str | None = None
    geometry: dict
    properties: dict | None = None
    conflict_id: int | None = None

    @field_validator("geometry")
    @classmethod
    def check_geom(cls, v: dict) -> dict:
        if not isinstance(v, dict) or v.get("type") not in GEOM_TYPES or "coordinates" not in v:
            raise ValueError("invalid GeoJSON geometry")
        return v


class MapFeatureUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    feature_type: str | None = None
    layer: str | None = None
    color: str | None = None
    geometry: dict | None = None
    properties: dict | None = None
    conflict_id: int | None = None


class MapFeatureOut(BaseModel):
    id: int
    name: str | None
    description: str | None
    feature_type: str
    layer: str
    color: str | None
    geometry: dict
    properties: dict | None
    conflict_id: int | None

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: int
    user: str
    action: str
    object_type: str
    object_id: int | None
    timestamp: datetime
    old_value: dict | None
    new_value: dict | None

    class Config:
        from_attributes = True

"""Legacy SQLite models for bootstrap fallback.

These mirror the management tables in a flat SQLite schema so the app
can read/write settings before the postgres connection is established.

.. deprecated::
    Once the first-time setup completes and postgres is configured,
    all data lives in ``management.*`` tables inside ``ultima_archive``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

legacy_metadata = MetaData()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _LegacyBase(DeclarativeBase):
    metadata = legacy_metadata


class SettingsModel(_LegacyBase):
    """Settings table in SQLite (bootstrap only)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    backend: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[str] = mapped_column(String)
    is_secret: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(String, default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class CentralJobModel(_LegacyBase):
    """Jobs table in SQLite (bootstrap only)."""

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    site: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    args_json: Mapped[str] = mapped_column(default="{}")
    auth_json: Mapped[str | None] = mapped_column(default=None)
    user_auth_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    last_event_at: Mapped[datetime | None] = mapped_column(default=None)
    result_success: Mapped[bool | None] = mapped_column(default=None)
    result_message: Mapped[str | None] = mapped_column(default=None)
    result_error: Mapped[str | None] = mapped_column(default=None)
    result_data_json: Mapped[str | None] = mapped_column(default=None)
    result_completed_at: Mapped[datetime | None] = mapped_column(default=None)


class CentralTaskModel(_LegacyBase):
    """Job tasks table in SQLite (bootstrap only)."""

    __tablename__ = "job_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    site: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    username: Mapped[str | None] = mapped_column(String(128), default=None)
    content_type: Mapped[str | None] = mapped_column(String(64), default=None)
    auth_id: Mapped[int | None] = mapped_column(Integer, default=None)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_total: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    last_event_at: Mapped[datetime | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)


class ProxyGeolocationModel(_LegacyBase):
    """Proxy geolocation cache in SQLite (bootstrap only)."""

    __tablename__ = "proxy_geolocation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), unique=True, index=True)
    proxy_url: Mapped[str | None] = mapped_column(String(512), index=True, default=None)
    ip_type: Mapped[str | None] = mapped_column(String(10), default=None)
    continent: Mapped[str | None] = mapped_column(String(50), default=None)
    country: Mapped[str | None] = mapped_column(String(100), default=None)
    country_code: Mapped[str | None] = mapped_column(String(5), default=None)
    region: Mapped[str | None] = mapped_column(String(100), default=None)
    city: Mapped[str | None] = mapped_column(String(100), default=None)
    latitude: Mapped[float | None] = mapped_column(default=None)
    longitude: Mapped[float | None] = mapped_column(default=None)
    postal: Mapped[str | None] = mapped_column(String(20), default=None)
    flag_emoji: Mapped[str | None] = mapped_column(String(10), default=None)
    flag_img: Mapped[str | None] = mapped_column(String(255), default=None)
    asn: Mapped[int | None] = mapped_column(default=None)
    org: Mapped[str | None] = mapped_column(String(255), default=None)
    isp: Mapped[str | None] = mapped_column(String(255), default=None)
    isp_domain: Mapped[str | None] = mapped_column(String(255), default=None)
    timezone_id: Mapped[str | None] = mapped_column(String(50), default=None)
    timezone_abbr: Mapped[str | None] = mapped_column(String(10), default=None)
    timezone_utc: Mapped[str | None] = mapped_column(String(10), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

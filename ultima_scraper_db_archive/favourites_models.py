"""Shared archive favourites. Leaf foreign keys are installed by Alembic."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, Sequence, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .databases.ultima_archive.schemas.templates.postgres_site import ManagementTemplate

SITES = ("onlyfans", "fansly", "loyalfans")
TARGETS = {"user": "users", "post": "x_posts", "story": "x_stories", "message": "x_messages"}
FAVOURITES_ID_SEQUENCE = Sequence("favourites_id_seq", schema="management")


class FavouriteModel(ManagementTemplate):
    __tablename__ = "favourites"
    __table_args__ = (
        UniqueConstraint("site", "entity_type", "entity_id", name="uq_favourites_entity"),
        CheckConstraint("created_at_source IN ('added', 'user_downloaded_at', 'user_join_date', 'legacy_favourite', 'migration_fallback')", name="ck_favourites_timestamp_source"),
        Index("idx_favourites_chronological", text("created_at DESC"), text("id DESC")),
        {"schema": "management", "postgresql_partition_by": "LIST (site)"},
    )
    site: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    id: Mapped[int] = mapped_column(BigInteger, FAVOURITES_ID_SEQUENCE, primary_key=True, server_default=FAVOURITES_ID_SEQUENCE.next_value())
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    created_at_source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="added")


class FavouritesMigrationModel(ManagementTemplate):
    """One durable checkpoint per site; fallback time never changes on resume."""
    __tablename__ = "favourites_migration"
    site: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    copied: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class FavouritesIdentityAuditModel(ManagementTemplate):
    """Immutable before/after mapping for the one-time chronological renumbering."""
    __tablename__ = "favourites_identity_audit"
    site: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    previous_id: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    previous_created_at_source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    source_join_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at_source: Mapped[str] = mapped_column(String(32), nullable=False)


def partition_names() -> set[str]:
    return {name for site in SITES for name in (
        f"favourites_{site}", *(f"favourites_{site}_{kind}" for kind in TARGETS)
    )}

"""PostgreSQL SQLAlchemy schemas for the UltimaScraper archive database.

This module provides database models optimized for PostgreSQL with:
- Native timezone-aware timestamps (TIMESTAMPTZ)
- Advanced indexing for performance
- JSONB for flexible data storage
- Async/await support via SQLAlchemy async session
- pgvector support for ML embeddings (future expansion)
"""

import uuid
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any, ClassVar, TypeGuard

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from ultima_scraper_db_archive.crypto import EncryptedText

metadata_obj = MetaData()

_CONTENT_MEDIA_OVERLAPS = "stories,posts,messages,mass_messages,media"
# PostgreSQL timezone-aware datetime type
TIMESTAMPTZ = TIMESTAMP(timezone=True)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _as_object_dict(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _as_optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    metadata = metadata_obj


class ManagementTemplate(Base):
    """Base class for management database models."""

    __abstract__ = True
    __table_args__ = {"schema": "management"}


class SiteTemplate(Base):
    """Base class for site-specific database models."""

    __abstract__ = True


class NativeIdMixin:
    """Keeps a string site identifier beside its BigInteger primary key.

    Sites with integer ids (OnlyFans, Fansly) store that id as ``id`` and leave
    ``external_id`` null. Sites with string ids (LoyalFans) store
    ``native_id_to_db_id(uid)`` as ``id`` and the string itself here. Lookups
    stay on ``id``, so this column needs no index.
    """

    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def native_id(self) -> str:
        """The identifier the site itself uses for this row."""
        return self.external_id or str(getattr(self, "id"))


class UserModel(NativeIdMixin, SiteTemplate):
    """Lightweight representation of a scraper user for PostgreSQL."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "idx_users_username_trgm",
            "username",
            postgresql_using="gin",
            postgresql_ops={"username": "public.gin_trgm_ops"},
        ),
        # Username lookups compare lower(username); sorts use it too.
        Index("idx_users_username_lower", text("lower(username)")),
        # Nearly every row is a probed non-performer, so index performers only.
        Index("idx_users_performer", "id", postgresql_where=text("performer IS TRUE")),
        Index(
            "idx_users_active_performer_cover",
            "id",
            postgresql_include=["active", "created_at"],
            postgresql_where=text("active IS TRUE AND performer IS TRUE"),
        ),
        Index("idx_users_created_at", text("created_at DESC NULLS LAST")),
        Index(
            "idx_users_downloaded_at_present",
            text("downloaded_at DESC NULLS LAST"),
            postgresql_where=text("downloaded_at IS NOT NULL"),
        ),
        Index(
            "idx_users_last_checked_coalesce",
            text("COALESCE(last_checked_at, updated_at) DESC NULLS LAST"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    balance: Mapped[float] = mapped_column(Float, server_default="0")
    spend: Mapped[bool] = mapped_column(Boolean, server_default="false")
    spender_type: Mapped[str | None] = mapped_column(
        String(32), server_default=None, nullable=True
    )  # "all", "free", or "paid"
    performer: Mapped[bool] = mapped_column(Boolean, server_default="false")
    favorite: Mapped[bool] = mapped_column(Boolean, server_default="false")
    watched: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ignored: Mapped[bool] = mapped_column(Boolean, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    join_date: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    # Relationships
    user_auths_info: Mapped[list["UserAuthModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_info: Mapped["UserInfoModel | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    subscriptions: Mapped[list["SubscriptionModel"]] = relationship(
        foreign_keys="SubscriptionModel.subscriber_id",
        back_populates="subscriber",
    )
    subscribers: Mapped[list["SubscriptionModel"]] = relationship(
        foreign_keys="SubscriptionModel.user_id",
    )
    favorite_users: Mapped[list["FavoriteUserModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    socials: Mapped[list["SocialModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    websites: Mapped[list["WebsiteModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    aliases: Mapped[list["UserAliasModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    remote_urls: Mapped[list["RemoteURLModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    supplied_content: Mapped[list["BoughtContentModel"]] = relationship(
        foreign_keys="BoughtContentModel.supplier_id",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
    bought_content: Mapped[list["BoughtContentModel"]] = relationship(
        foreign_keys="BoughtContentModel.buyer_id",
        back_populates="buyer",
        cascade="all, delete-orphan",
    )
    histo_user_infos: Mapped[list["HistoUserInfoModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to the current UTC time."""
        self.updated_at = utcnow()

    @property
    def is_active(self) -> bool:
        """Flag indicating if the account is active and not archived."""
        return bool(self.active)


class UserAuthModel(SiteTemplate):
    """Stored authentication details for user accounts."""

    __tablename__ = "user_auths"
    __table_args__ = (
        UniqueConstraint("cookie", "authorization", name="uq_user_auths_cookie_auth"),
        Index("idx_user_auths_user_id", "user_id"),
        Index("idx_user_auths_site", "site"),
        Index("idx_user_auths_username", "username"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    cookie: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    x_bc: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    authorization: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    user_agent: Mapped[str] = mapped_column(EncryptedText())
    email: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    password: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    proxy_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), server_default="unknown")
    last_tested_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Age verification fields (OnlyFans-specific)
    is_age_verified: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=None
    )
    age_verification_required: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=None
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="user_auths_info")

    def touch(self) -> None:
        """Update modification timestamp."""
        self.updated_at = utcnow()


class UserInfoModel(SiteTemplate):
    """User profile information and statistics."""

    __tablename__ = "user_infos"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_infos_user_id"),
        # Almost every profile is free and never downloaded, and the
        # demographic/flag columns are almost always NULL or false: index only
        # the rows a filter can select.
        Index("idx_user_infos_price_paid", "price", postgresql_where=text("price > 0")),
        Index(
            "idx_user_infos_paid_video_cover",
            "price",
            "user_id",
            postgresql_include=["video_count", "sex", "partner_sex"],
            postgresql_where=text("price > 0 AND video_count > 0"),
        ),
        Index(
            "idx_user_infos_downloaded_at_present",
            text("downloaded_at DESC NULLS LAST"),
            postgresql_where=text("downloaded_at IS NOT NULL"),
        ),
        *(
            Index(
                f"idx_user_infos_{column}",
                column,
                postgresql_where=text(f"{column} IS NOT NULL"),
            )
            for column in (
                "sex",
                "gender",
                "profile_type",
                "sexual_content",
                "partner_sex",
                "partner_gender",
            )
        ),
        *(
            Index(
                f"idx_user_infos_{column}",
                "user_id",
                postgresql_where=text(f"{column} IS TRUE"),
            )
            for column in ("verified", "ai_assisted")
        ),
        Index(
            "idx_user_infos_media_count",
            text("media_count DESC NULLS LAST"),
        ),
        Index(
            "idx_user_infos_desc_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "public.gin_trgm_ops"},
            postgresql_where=text("description IS NOT NULL AND description != ''"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, server_default="0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sex: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    gender: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    profile_type: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sexual_content: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    partner_sex: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    partner_gender: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    verified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    post_count: Mapped[int] = mapped_column(Integer, server_default="0")
    media_count: Mapped[int] = mapped_column(Integer, server_default="0")
    image_count: Mapped[int] = mapped_column(Integer, server_default="0")
    video_count: Mapped[int] = mapped_column(Integer, server_default="0")
    audio_count: Mapped[int] = mapped_column(Integer, server_default="0")
    stream_count: Mapped[int] = mapped_column(Integer, server_default="0")
    archived_post_count: Mapped[int] = mapped_column(Integer, server_default="0")
    private_archived_post_count: Mapped[int] = mapped_column(
        Integer, server_default="0"
    )
    favourited_count: Mapped[int] = mapped_column(Integer, server_default="0")
    favourites_count: Mapped[int] = mapped_column(Integer, server_default="0")
    subscribers_count: Mapped[int] = mapped_column(Integer, server_default="0")
    size: Mapped[int] = mapped_column(BigInteger, server_default="0")
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    first_downloaded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="user_info")


class SubscriptionModel(SiteTemplate):
    """User subscription relationships."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "subscriber_id", name="uq_subscriptions_user_subscriber"
        ),
        Index("idx_subscriptions_user_id", "user_id"),
        Index("idx_subscriptions_subscriber_id", "subscriber_id"),
        Index("idx_subscriptions_active", "active"),
        Index("idx_subscriptions_user_id_active", "user_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    subscriber_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    paid_content: Mapped[bool] = mapped_column(Boolean, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    renewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    subscriber: Mapped[UserModel] = relationship(
        foreign_keys=[subscriber_id],
        back_populates="subscriptions",
    )


class InvalidUserModel(SiteTemplate):
    """User IDs confirmed missing from the upstream API."""

    __tablename__ = "invalid_users"
    __table_args__ = (
        UniqueConstraint("site", "user_id", name="uq_invalid_users_site_user"),
        Index("idx_invalid_users_user_id", "user_id"),
        Index("idx_invalid_users_last_checked", "last_checked_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    def touch(self) -> None:
        """Update modification timestamp."""

        self.updated_at = utcnow()


class FavoriteUserModel(SiteTemplate):
    """Favorite users marked by a user."""

    __tablename__ = "favorite_users"
    __table_args__ = (UniqueConstraint("user_id", name="uq_favorite_users_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    notification: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="favorite_users")


class SocialModel(SiteTemplate):
    """Social media links associated with a user."""

    __tablename__ = "socials"
    __table_args__ = (
        Index("idx_socials_user_id", "user_id"),
        Index("idx_socials_site_identifier", "site", "identifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    site: Mapped[str] = mapped_column(String(128))
    identifier: Mapped[str] = mapped_column(Text)

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="socials")


class WebsiteModel(SiteTemplate):
    """Tracked website URLs associated with a user."""

    __tablename__ = "websites"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_websites_user_url"),
        Index("idx_websites_user_id", "user_id"),
    )

    # Matches the BIGSERIAL created by migration f2c4e8a1b9d7.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="websites")


class UserProfileMediaModel(SiteTemplate):
    """Historical tracking of user avatar and header URLs."""

    __tablename__ = "user_profile_media"
    __table_args__ = (
        Index("idx_user_profile_media_user_id", "user_id"),
        Index("idx_user_profile_media_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )


class MediaModel(NativeIdMixin, SiteTemplate):
    """Media files associated with content."""

    __tablename__ = "media"
    __table_args__ = (
        Index(
            "idx_media_userid_url_not_null",
            "user_id",
            postgresql_where=text("url IS NOT NULL"),
        ),
        Index("idx_media_user_id", "user_id"),
        Index("idx_media_userid_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # This size is from a head request, not the disk. If it's DRM-protected, it may be None until after download when we can check the file size on disk.
    size: Mapped[int] = mapped_column(BigInteger, server_default="0")
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    drm: Mapped[bool] = mapped_column(Boolean, server_default="false")
    category: Mapped[str] = mapped_column(String(64), nullable=True)
    preview: Mapped[bool] = mapped_column(Boolean, server_default="false")
    downloaded: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)

    # Relationships
    drm_manifest: Mapped["DRMManifestModel | None"] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )
    media_urls: Mapped[list["MediaUrlModel"]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )
    stories: Mapped[list["StoryModel"]] = relationship(
        secondary="content_media_asso",
        back_populates="media",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    posts: Mapped[list["PostModel"]] = relationship(
        secondary="content_media_asso",
        back_populates="media",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    messages: Mapped[list["MessageModel"]] = relationship(
        secondary="content_media_asso",
        back_populates="media",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    mass_messages: Mapped[list["MassMessageModel"]] = relationship(
        secondary="content_media_asso",
        back_populates="media",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    filepaths: Mapped[list["FilePathModel"]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
    )


class MediaUrlModel(SiteTemplate):
    """Auth-scoped URLs for media items."""

    __tablename__ = "media_urls"
    __table_args__ = (
        UniqueConstraint("media_id", "auth_id", name="uq_media_urls_media_auth"),
        Index("idx_media_urls_media_id", "media_id"),
        Index("idx_media_urls_auth_id", "auth_id"),
        Index("idx_media_urls_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE")
    )
    auth_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    media: Mapped[MediaModel] = relationship(back_populates="media_urls")

    def is_expired(self) -> bool:
        """Check if this URL has expired."""
        if self.expires_at is None:
            return False  # Unknown expiry = assume valid
        return self.expires_at < utcnow()


class DRMManifestModel(SiteTemplate):
    """DRM manifest and signature data for protected media."""

    __tablename__ = "drm_manifest"
    __table_args__ = (Index("idx_drm_manifest_media_id", "media_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE")
    )
    hls_manifest: Mapped[str | None] = mapped_column(Text, nullable=True)
    dash_manifest: Mapped[str | None] = mapped_column(Text, nullable=True)
    hls_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    hls_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    hls_key_pair_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dash_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    dash_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    dash_key_pair_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # These sizes are from a head request, not the disk
    video_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    audio_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    media: Mapped["MediaModel | None"] = relationship(back_populates="drm_manifest")


class ContentMediaAssoModel(SiteTemplate):
    """Association table linking content to media."""

    __tablename__ = "content_media_asso"
    __table_args__ = (
        UniqueConstraint("story_id", "media_id", name="uq_content_media_story_media"),
        UniqueConstraint("post_id", "media_id", name="uq_content_media_post_media"),
        UniqueConstraint(
            "message_id", "media_id", name="uq_content_media_message_media"
        ),
        UniqueConstraint(
            "mass_message_id", "media_id", name="uq_content_media_mass_message_media"
        ),
        Index("ix_content_media_story_id", "story_id"),
        Index("ix_content_media_post_id", "post_id"),
        Index("ix_content_media_message_id", "message_id"),
        Index("ix_content_media_mass_message_id", "mass_message_id"),
        Index("ix_content_media_media_id", "media_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    story_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("x_stories.id", ondelete="CASCADE"),
        nullable=True,
    )
    post_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("x_posts.id", ondelete="CASCADE"),
        nullable=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("x_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    mass_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("x_mass_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE")
    )


class StoryModel(NativeIdMixin, SiteTemplate):
    """Story content from user timeline."""

    __tablename__ = "x_stories"
    __table_args__ = (
        Index("idx_x_stories_user_id", "user_id"),
        Index("idx_x_stories_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, default=None)

    # Relationships
    media: Mapped[list[MediaModel]] = relationship(
        secondary="content_media_asso",
        back_populates="stories",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    mentions: Mapped[list["ContentMentionModel"]] = relationship(
        foreign_keys="ContentMentionModel.story_id",
        back_populates="story",
        cascade="all, delete-orphan",
    )


class PostModel(NativeIdMixin, SiteTemplate):
    """Post content from user timeline."""

    __tablename__ = "x_posts"
    __table_args__ = (
        Index("idx_x_posts_user_id", "user_id"),
        Index("idx_x_posts_created_at", "created_at"),
        Index(
            "idx_x_posts_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "public.gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, server_default="0")
    deleted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, server_default="false")
    paid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    media_count: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)

    # Relationships
    media: Mapped[list[MediaModel]] = relationship(
        secondary="content_media_asso",
        back_populates="posts",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    linked_posts: Mapped[list["LinkedPostModel"]] = relationship(
        foreign_keys="LinkedPostModel.post_id",
        back_populates="post",
        cascade="all, delete-orphan",
    )
    mentions: Mapped[list["ContentMentionModel"]] = relationship(
        foreign_keys="ContentMentionModel.post_id",
        back_populates="post",
        cascade="all, delete-orphan",
    )


class MessageModel(NativeIdMixin, SiteTemplate):
    """Direct message content."""

    __tablename__ = "x_messages"
    __table_args__ = (
        Index("idx_x_messages_user_id", "user_id"),
        Index("idx_x_messages_receiver_id", "receiver_id"),
        Index("idx_x_messages_created_at", "created_at"),
        Index(
            "idx_x_messages_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "public.gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    receiver_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    queue_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_mass_messages.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, server_default="0")
    deleted: Mapped[bool] = mapped_column(Boolean, server_default="false")
    paid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    liked: Mapped[bool] = mapped_column(Boolean, server_default="false")
    verified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    media_count: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)

    # Relationships
    media: Mapped[list[MediaModel]] = relationship(
        secondary="content_media_asso",
        back_populates="messages",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    mentions: Mapped[list["ContentMentionModel"]] = relationship(
        foreign_keys="ContentMentionModel.message_id",
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MassMessageStatModel(NativeIdMixin, SiteTemplate):
    """Statistics for mass messages sent by a user."""

    __tablename__ = "mass_message_stats"
    __table_args__ = (Index("idx_mass_message_stats_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    media_count: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    buyer_count: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    sent_count: Mapped[int] = mapped_column(Integer, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, server_default="0")


class MassMessageModel(NativeIdMixin, SiteTemplate):
    """Mass message content sent to multiple users."""

    __tablename__ = "x_mass_messages"
    __table_args__ = (
        Index("idx_x_mass_messages_user_id", "user_id"),
        Index("idx_x_mass_messages_created_at", "created_at"),
        Index(
            "idx_x_mass_messages_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "public.gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, server_default="0")
    media_count: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)

    # Relationships
    media: Mapped[list[MediaModel]] = relationship(
        secondary="content_media_asso",
        back_populates="mass_messages",
        overlaps=_CONTENT_MEDIA_OVERLAPS,
    )
    mentions: Mapped[list["ContentMentionModel"]] = relationship(
        foreign_keys="ContentMentionModel.mass_message_id",
        back_populates="mass_message",
        cascade="all, delete-orphan",
    )


class WebSocketMessageModel(SiteTemplate):
    """Raw WebSocket message payloads for audit/debugging."""

    __tablename__ = "websocket_messages"
    __table_args__ = (
        Index("idx_websocket_messages_user_id", "site_account_user_id"),
        Index("idx_websocket_messages_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_account_user_id: Mapped[int] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    payload: Mapped[str] = mapped_column(Text)


class CommentModel(NativeIdMixin, SiteTemplate):
    """Comments on posts."""

    __tablename__ = "comments"
    __table_args__ = (
        Index("idx_comments_post_id", "post_id"),
        Index("idx_comments_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE")
    )
    reply_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger)
    giphy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    likes_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


class UserAliasModel(SiteTemplate):
    """Username aliases for user lookups and history."""

    __tablename__ = "user_aliases"
    __table_args__ = (
        Index(
            "idx_user_aliases_username_trgm",
            "username",
            postgresql_using="gin",
            postgresql_ops={"username": "public.gin_trgm_ops"},
        ),
        Index("idx_user_aliases_username_lower", text("lower(username)")),
        UniqueConstraint("user_id", "username", name="uq_user_aliases_user_username"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="aliases")


class FilePathModel(SiteTemplate):
    """Local file paths for downloaded media."""

    __tablename__ = "filepaths"
    __table_args__ = (
        Index("idx_filepaths_media_id", "media_id"),
        Index("idx_filepaths_filepath", "filepath"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("media.id", ondelete="CASCADE")
    )
    filepath: Mapped[str] = mapped_column(String(255))
    preview: Mapped[bool] = mapped_column(Boolean, server_default="false")
    downloaded: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    media: Mapped[MediaModel] = relationship(back_populates="filepaths")


class RemoteURLModel(SiteTemplate):
    """Remote URLs with upload/download tracking."""

    __tablename__ = "remote_urls"
    __table_args__ = (Index("idx_remote_urls_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    downloaded_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="remote_urls")


class BoughtContentModel(SiteTemplate):
    """Purchased/paid content relationships between users."""

    __tablename__ = "bought_content"
    __table_args__ = (
        Index("idx_bought_content_supplier_id", "supplier_id"),
        Index("idx_bought_content_buyer_id", "buyer_id"),
        Index("idx_bought_content_post_id", "post_id"),
        Index("idx_bought_content_message_id", "message_id"),
        Index("idx_bought_content_buyer_post_id", "buyer_id", "post_id", unique=True),
        Index(
            "idx_bought_content_buyer_message_id",
            "buyer_id",
            "message_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    buyer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    post_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_messages.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    supplier: Mapped[UserModel] = relationship(
        foreign_keys=[supplier_id], back_populates="supplied_content"
    )
    buyer: Mapped[UserModel] = relationship(
        foreign_keys=[buyer_id], back_populates="bought_content"
    )


class HistoUserInfoModel(SiteTemplate):
    """Historical snapshots of user profile changes over time."""

    __tablename__ = "histo_user_infos"
    __table_args__ = (
        Index("idx_histo_user_infos_user_id", "user_id"),
        Index("idx_histo_user_infos_created_at", "created_at"),
        Index(
            "idx_histo_user_infos_desc_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "public.gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, server_default="0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion: Mapped[bool] = mapped_column(Boolean, server_default="false")
    post_count: Mapped[int] = mapped_column(Integer, server_default="0")
    media_count: Mapped[int] = mapped_column(Integer, server_default="0")
    image_count: Mapped[int] = mapped_column(Integer, server_default="0")
    video_count: Mapped[int] = mapped_column(Integer, server_default="0")
    audio_count: Mapped[int] = mapped_column(Integer, server_default="0")
    stream_count: Mapped[int] = mapped_column(Integer, server_default="0")
    archived_post_count: Mapped[int] = mapped_column(Integer, server_default="0")
    private_archived_post_count: Mapped[int] = mapped_column(
        Integer, server_default="0"
    )
    favourited_count: Mapped[int] = mapped_column(Integer, server_default="0")
    favourites_count: Mapped[int] = mapped_column(Integer, server_default="0")
    subscribers_count: Mapped[int] = mapped_column(Integer, server_default="0")
    size: Mapped[int] = mapped_column(BigInteger, server_default="0")
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    user: Mapped[UserModel] = relationship(back_populates="histo_user_infos")


class LinkedPostModel(SiteTemplate):
    """Links between related posts (threads, quotes, references)."""

    __tablename__ = "linked_posts"
    __table_args__ = (
        Index("idx_linked_posts_post_id", "post_id"),
        Index("idx_linked_posts_linked_post_id", "linked_post_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE")
    )
    linked_post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE")
    )

    # Relationships
    post: Mapped["PostModel"] = relationship(
        foreign_keys=[post_id], back_populates="linked_posts"
    )
    linked_post: Mapped["PostModel"] = relationship(foreign_keys=[linked_post_id])


class ContentMentionModel(SiteTemplate):
    """A user handle or name mentioned by one archived content item."""

    __tablename__ = "content_mentions"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(post_id, message_id, mass_message_id, story_id) = 1",
            name="ck_content_mentions_one_content",
        ),
        Index("idx_content_mentions_post_id", "post_id"),
        Index("idx_content_mentions_message_id", "message_id"),
        Index("idx_content_mentions_mass_message_id", "mass_message_id"),
        Index("idx_content_mentions_story_id", "story_id"),
        Index("idx_content_mentions_mentioned_user_id", "mentioned_user_id"),
        Index("idx_content_mentions_normalized", "normalized_mention"),
        # Used by mention backfill duplicate checks. Generate the migration yourself.
        Index("idx_content_mentions_post_lookup", "post_id", "mention_kind", "normalized_mention"),
        Index("idx_content_mentions_message_lookup", "message_id", "mention_kind", "normalized_mention"),
        Index("idx_content_mentions_mass_message_lookup", "mass_message_id", "mention_kind", "normalized_mention"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_messages.id", ondelete="CASCADE"), nullable=True
    )
    mass_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("x_mass_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    story_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("x_stories.id", ondelete="CASCADE"), nullable=True
    )
    mentioned_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    raw_mention: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_mention: Mapped[str] = mapped_column(String(512), nullable=False)
    mention_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="platform_tag"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )

    # Relationships
    post: Mapped["PostModel"] = relationship(
        foreign_keys=[post_id], back_populates="mentions"
    )
    message: Mapped["MessageModel"] = relationship(
        foreign_keys=[message_id], back_populates="mentions"
    )
    mass_message: Mapped["MassMessageModel"] = relationship(
        foreign_keys=[mass_message_id], back_populates="mentions"
    )
    story: Mapped["StoryModel"] = relationship(
        foreign_keys=[story_id], back_populates="mentions"
    )
    mentioned_user: Mapped[UserModel | None] = relationship(
        foreign_keys=[mentioned_user_id]
    )


class LinkedUserModel(SiteTemplate):
    """Deprecated legacy post-user links retained during the transition.

    ``ContentMentionModel`` is the active model.  This mapping deliberately
    remains in metadata so Alembic does not mistake existing archive tables for
    stale objects and generate destructive ``DROP TABLE`` migrations.
    """

    __tablename__ = "linked_users"
    __table_args__ = (
        Index("idx_linked_users_post_id", "post_id"),
        Index("idx_linked_users_linked_user_id", "linked_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("x_posts.id", ondelete="CASCADE")
    )
    linked_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )


class StatisticsModel(SiteTemplate):
    """Daily site-wide media size statistics snapshot."""

    __tablename__ = "statistics"
    __table_args__ = (
        UniqueConstraint("bucket_date", name="uq_statistics_bucket_date"),
        Index("idx_statistics_bucket_date", "bucket_date", unique=True),
        Index("idx_statistics_calculated_at", "calculated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False)
    bucket_started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    bucket_ends_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        server_default=func.now(),
        nullable=False,
    )

    total_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    sized_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    zero_size_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")

    image_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    image_sized_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    video_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    video_sized_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    audio_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    audio_sized_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    other_media_count: Mapped[int] = mapped_column(BigInteger, server_default="0")
    other_sized_count: Mapped[int] = mapped_column(BigInteger, server_default="0")

    total_known_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    avg_media_size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    avg_image_size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    avg_video_size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    avg_audio_size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    avg_other_size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
    size_coverage_ratio: Mapped[float] = mapped_column(Float, server_default="0")
    user_record_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    performer_profile_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    active_user_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    archived_content_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    post_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    story_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mass_message_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    downloaded_media_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )


class SettingsModel(ManagementTemplate):
    """Global settings stored in the management schema."""

    __tablename__ = "settings"
    __table_args__ = (
        Index("idx_settings_backend", "backend"),
        Index("idx_settings_key", "key"),
        Index("idx_settings_id_version", "id", "version"),
        Index("uq_settings_config_authority", "backend", "key", unique=True, postgresql_where=text("key IN ('config', 'config_scope')")),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    backend: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(Text)  # JSON string
    is_secret: Mapped[bool] = mapped_column(Boolean, server_default="false")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )


class SearchLoadoutModel(ManagementTemplate):
    """WebUI search loadouts stored in a dedicated management table."""

    __tablename__ = "search_loadouts"
    __table_args__ = (
        UniqueConstraint("loadout_type", "name", name="uq_search_loadouts_type_name"),
        Index("idx_search_loadouts_type", "loadout_type"),
        Index("idx_search_loadouts_is_default", "is_default"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    loadout_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(90), nullable=False)
    identifier: Mapped[str] = mapped_column(Text, server_default="")
    description: Mapped[str] = mapped_column(Text, server_default="")
    site: Mapped[str] = mapped_column(String(32), server_default="")
    filters_json: Mapped[str] = mapped_column(Text, server_default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )


class BackendInventoryModel(ManagementTemplate):
    """Backend inventory and scope linkage rows."""

    __tablename__ = "backends"
    __table_args__ = (
        Index("idx_backends_hostname", "hostname", unique=True),
        Index("idx_backends_settings_id", "settings_id"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backend_name: Mapped[str] = mapped_column(Text, nullable=False)
    hostname: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    local_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    settings_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("management.settings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )

    settings: Mapped[SettingsModel] = relationship()


class ClusterModel(ManagementTemplate):
    """The one row naming this database's cluster.

    Every backend that shares this database reports the same cluster_id, which
    is how a WebUI tells one cluster from several independent backends.
    """

    __tablename__ = "cluster"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_cluster_single_row"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default="1")
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    # What the people using the cluster call it; shown by every WebUI.
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A fixed value encrypted with USR_SECRET_KEY; see secret_key_check.py.
    secret_key_check: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClusterClientModel(ManagementTemplate):
    """A client (a WebUI) allowed into the cluster, with its own credential.

    Only the SHA-256 of the client's token is kept. Revoking sets revoked_at;
    every backend then refuses the token.
    """

    __tablename__ = "cluster_clients"
    __table_args__ = (
        Index("idx_cluster_clients_token_hash", "token_hash", unique=True),
        {"schema": "management"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="webui")
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)


class ClusterInviteModel(ManagementTemplate):
    """A one-time, expiring code that lets one client join the cluster.

    Only the SHA-256 of the code is kept.
    """

    __tablename__ = "cluster_invites"
    __table_args__ = (
        Index("idx_cluster_invites_code_hash", "code_hash", unique=True),
        {"schema": "management"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # The client that made it, or "admin" for a backend admin token.
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("management.cluster_clients.id", ondelete="SET NULL"),
        nullable=True,
    )


class BackendPeerModel(ManagementTemplate):
    """A backend's token for calling other backends on this database.

    Only the SHA-256 of the token is kept. Revoking sets revoked_at; every
    backend then refuses it, and that backend does not issue itself another.
    """

    __tablename__ = "backend_peers"
    __table_args__ = (
        Index("idx_backend_peers_token_hash", "token_hash", unique=True),
        {"schema": "management"},
    )

    backend_id: Mapped[str] = mapped_column(Text, primary_key=True)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)


class SiteModel(ManagementTemplate):
    """Supported sites for order entries."""

    __tablename__ = "sites"
    __table_args__ = (
        Index("idx_sites_name", "name", unique=True),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    orders: Mapped[list["OrderModel"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    ordered_performers: Mapped[list["OrderedPerformerModel"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    ordered_ppv: Mapped[list["OrderedPpvModel"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )


class OrderModel(ManagementTemplate):
    """Order header record."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_orders_site_id", "site_id"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("management.sites.id"))
    order_type: Mapped[str] = mapped_column(String(32), default="subscription")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    total_price: Mapped[float | None] = mapped_column(Float, default=None)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    spender_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    site: Mapped[SiteModel] = relationship(back_populates="orders")
    ordered_performers: Mapped[list["OrderedPerformerModel"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    ordered_ppv: Mapped[list["OrderedPpvModel"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utcnow()


class OrderedPerformerModel(ManagementTemplate):
    """Performer subscription / PPV order line item."""

    __tablename__ = "ordered_performers"
    __table_args__ = (
        Index("idx_ordered_performers_order_id", "order_id"),
        Index("idx_ordered_performers_site_id", "site_id"),
        Index("idx_ordered_performers_user_id", "user_id"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("management.orders.id")
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("management.sites.id"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(Text, default=None)
    price: Mapped[float | None] = mapped_column(Float, default=None)
    post_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    content_type: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    spender_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    order: Mapped[OrderModel] = relationship(back_populates="ordered_performers")
    site: Mapped[SiteModel] = relationship(back_populates="ordered_performers")

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utcnow()


class OrderedPpvModel(ManagementTemplate):
    """PPV order line item."""

    __tablename__ = "ordered_ppv"
    __table_args__ = (
        Index("idx_ordered_ppv_order_id", "order_id"),
        Index("idx_ordered_ppv_site_id", "site_id"),
        Index("idx_ordered_ppv_user_id", "user_id"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("management.orders.id")
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("management.sites.id"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    post_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    price: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    spender_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    order: Mapped[OrderModel] = relationship(back_populates="ordered_ppv")
    site: Mapped[SiteModel] = relationship(back_populates="ordered_ppv")

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utcnow()


class CentralJobModel(ManagementTemplate):
    """Cross-site job tracking stored in the management schema."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_job_type", "job_type"),
        Index("idx_jobs_site", "site"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_worker_id", "worker_id"),
        {"schema": "management"},
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64))
    site: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), server_default="pending")
    priority: Mapped[int] = mapped_column(Integer, server_default="0")
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, server_default="3")
    args_json: Mapped[str] = mapped_column(Text, server_default="{}")
    job_config_json: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)
    auth_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_auth_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    result_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMPTZ, nullable=True
    )

    JSON_EMPTY: ClassVar[str] = "{}"


class CentralTaskModel(ManagementTemplate):
    """Cross-site task tracking stored in the management schema."""

    __tablename__ = "job_tasks"
    __table_args__ = (
        Index("idx_job_tasks_job_id", "job_id"),
        Index("idx_job_tasks_task_type", "task_type"),
        Index("idx_job_tasks_status", "status"),
        Index("idx_job_tasks_site", "site"),
        # Per-job error summaries read only the failed rows.
        Index(
            "idx_job_tasks_job_errors",
            "job_id",
            "error",
            postgresql_where=text("error IS NOT NULL"),
        ),
        {"schema": "management", "postgresql_partition_by": "LIST (job_id)"},
    )

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), server_default="pending")
    site: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auth_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_processed: Mapped[int] = mapped_column(Integer, server_default="0")
    items_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition_json: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)


class ProxyGeolocationModel(ManagementTemplate):
    """Cached geolocation data for a proxy's public IP address."""

    __tablename__ = "proxy_geolocation"
    __table_args__ = (
        Index("idx_proxy_geolocation_ip", "ip", unique=True),
        Index("idx_proxy_geolocation_proxy_url", "proxy_url"),
        {"schema": "management"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), unique=True)  # IPv4 or IPv6
    proxy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Geolocation fields
    ip_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    continent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    postal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Flag
    flag_emoji: Mapped[str | None] = mapped_column(String(10), nullable=True)
    flag_img: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Connection / ISP
    asn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    isp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    isp_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Timezone
    timezone_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timezone_abbr: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone_utc: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Metadata
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)

    def to_geolocation_dict(self) -> dict[str, object]:
        """Convert to a dict matching the ``GeolocationData`` TypedDict."""
        return {
            "ip": self.ip,
            "proxy_url": self.proxy_url,
            "success": True,
            "type": self.ip_type,
            "continent": self.continent,
            "country": self.country,
            "country_code": self.country_code,
            "region": self.region,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "postal": self.postal,
            "flag": {
                "emoji": self.flag_emoji,
                "img": self.flag_img,
            },
            "connection": {
                "asn": self.asn,
                "org": self.org,
                "isp": self.isp,
                "domain": self.isp_domain,
            },
            "timezone": {
                "id": self.timezone_id,
                "abbr": self.timezone_abbr,
                "utc": self.timezone_utc,
            },
        }

    @classmethod
    def from_geolocation_dict(
        cls, data: dict[str, object], proxy_url: str | None = None
    ) -> "ProxyGeolocationModel":
        """Create a model instance from an ipwho.is JSON response."""
        connection = _as_object_dict(data.get("connection"))
        tz = _as_object_dict(data.get("timezone"))
        flag = _as_object_dict(data.get("flag"))
        ip_value = _as_optional_str(data.get("ip"))
        if not ip_value:
            raise ValueError("Geolocation payload is missing an IP address")
        return cls(
            ip=ip_value,
            proxy_url=proxy_url or _as_optional_str(data.get("proxy_url")),
            ip_type=_as_optional_str(data.get("type")),
            continent=_as_optional_str(data.get("continent")),
            country=_as_optional_str(data.get("country")),
            country_code=_as_optional_str(data.get("country_code")),
            region=_as_optional_str(data.get("region")),
            city=_as_optional_str(data.get("city")),
            latitude=_as_optional_float(data.get("latitude")),
            longitude=_as_optional_float(data.get("longitude")),
            postal=_as_optional_str(data.get("postal")),
            flag_emoji=_as_optional_str(flag.get("emoji")),
            flag_img=_as_optional_str(flag.get("img")),
            asn=_as_optional_int(connection.get("asn")),
            org=_as_optional_str(connection.get("org")),
            isp=_as_optional_str(connection.get("isp")),
            isp_domain=_as_optional_str(connection.get("domain")),
            timezone_id=_as_optional_str(tz.get("id")),
            timezone_abbr=_as_optional_str(tz.get("abbr")),
            timezone_utc=_as_optional_str(tz.get("utc")),
        )


content_types = StoryModel | PostModel | MessageModel | MassMessageModel

# Import after model construction to avoid the API/schema initialization cycle.
from ultima_scraper_api import SUPPORTED_SITES  # noqa: E402


def create_merged_metadata(base: type[DeclarativeBase] | Any) -> MetaData:
    """Create a merged MetaData object with schemas for all supported sites."""
    site_metadatas: list[MetaData] = []
    for supp_site in SUPPORTED_SITES:
        site_metadatas.append(MetaData(schema=supp_site.lower()))

    merged_metadata = MetaData()

    for _k, t in base.metadata.tables.items():
        if not t.schema:
            # Duplicate table for each site schema
            for site_metadata in site_metadatas:

                def referred_schema_fn(
                    table: Any,
                    to_schema: Any,
                    constraint: Any,
                    referred_schema: str | None,
                ):
                    if referred_schema is not None:
                        return referred_schema
                    return site_metadata.schema

                new_table = t.to_metadata(site_metadata)
                new_table.to_metadata(
                    merged_metadata, referred_schema_fn=referred_schema_fn
                )
        else:
            # Keep table in its original schema (e.g., management)
            t.to_metadata(merged_metadata)

    return merged_metadata




class MPSPlanModel(ManagementTemplate):
    """Durable selection and execution checkpoint for a mass profile job."""

    __tablename__ = "mps_plans"
    __table_args__ = (
        CheckConstraint(
            "total >= 0 AND cursor >= 0 AND cursor <= total", name="ck_mps_plan_cursor"
        ),
        Index("idx_mps_plans_status_job", "status", "job_id"),
        Index("idx_mps_plans_parent_job", "parent_job_id"),
        {"schema": "management"},
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey(
            "management.mps_plans.job_id", name="fk_mps_plan_parent", ondelete="CASCADE"
        ),
    )
    site: Mapped[str] = mapped_column(String(64))
    job_config_json: Mapped[str] = mapped_column(Text)
    selection_json: Mapped[str] = mapped_column(Text)
    proxy_pool_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), server_default="ready")
    total: Mapped[int] = mapped_column(BigInteger)
    cursor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    completed: Mapped[int] = mapped_column(BigInteger, server_default="0")
    failed: Mapped[int] = mapped_column(BigInteger, server_default="0")
    summary_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class MPSCandidateRangeModel(ManagementTemplate):
    """Disjoint candidate ranges; even sparse selections stay in PostgreSQL."""

    __tablename__ = "mps_candidate_ranges"
    __table_args__ = (
        CheckConstraint(
            "first_ordinal >= 0 AND start_id > 0 AND end_id >= start_id",
            name="ck_mps_candidate_range",
        ),
        {"schema": "management"},
    )

    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("management.mps_plans.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    start_id: Mapped[int] = mapped_column(BigInteger)
    end_id: Mapped[int] = mapped_column(BigInteger)


class MPSTaskDefinitionModel(ManagementTemplate):
    """Paged explicit tasks; a plan activates a fully uploaded definition."""

    __tablename__ = "mps_task_definitions"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_mps_task_definition_ordinal"),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_mps_task_definition_status",
        ),
        UniqueConstraint("manifest_id", "task_id", name="uq_mps_definition_task"),
        Index(
            "idx_mps_definition_pending", "manifest_id", "ordinal",
            postgresql_where=text("status = 'pending'"),
        ),
        {"schema": "management"},
    )

    manifest_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("management.mps_plans.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64))
    task_json: Mapped[str] = mapped_column(Text)
    dependency_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    status: Mapped[str] = mapped_column(String(32), server_default="pending")


class MPSRetryTaskModel(ManagementTemplate):
    """Frozen retry inputs, consumed alongside committed definition pages."""

    __tablename__ = "mps_retry_tasks"
    __table_args__ = (
        CheckConstraint("ordinal >= 0 AND read_bytes > 0", name="ck_mps_retry_task_bounds"),
        {"schema": "management"},
    )

    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("management.mps_plans.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64))
    read_bytes: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class DatabaseWriteReceiptModel(ManagementTemplate):
    """Committed writer outcomes; Redis is only their bounded delivery cache."""

    __tablename__ = "database_write_receipts"
    __table_args__ = (
        Index("idx_write_receipts_age", "committed_at", postgresql_using="brin"),
        Index("idx_write_receipts_run_command", "run_id", "command_id", postgresql_where=text("run_id IS NOT NULL")),
        {"schema": "management"},
    )

    command_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operation: Mapped[str] = mapped_column(String(64))
    site: Mapped[str | None] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    failed_command_json: Mapped[str | None] = mapped_column(Text)
    post_commit_json: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )


class TaskMediaPlanModel(ManagementTemplate):
    """Durable scrape/download selection header; Redis carries only its ID."""

    __tablename__ = "task_media_plans"
    __table_args__ = {"schema": "management"}

    selection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(64))
    site: Mapped[str] = mapped_column(String(64))
    auth_id: Mapped[int | None] = mapped_column(BigInteger)
    ready: Mapped[bool] = mapped_column(Boolean, server_default="false")
    total: Mapped[int] = mapped_column(BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class TaskMediaSelectionModel(ManagementTemplate):
    """Selected media identity and signatures, paged by owner, type and media ID."""

    __tablename__ = "task_media_selections"
    __table_args__ = {"schema": "management"}

    selection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("management.task_media_plans.selection_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    media_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_id: Mapped[int] = mapped_column(BigInteger)
    content_created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    url: Mapped[str | None] = mapped_column(Text)
    drm_json: Mapped[str | None] = mapped_column(Text)


class TaskMediaEvidenceModel(ManagementTemplate):
    """Individual download results and scrape errors kept outside task blobs."""

    __tablename__ = "task_media_evidence"
    __table_args__ = {"schema": "management"}

    selection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("management.task_media_plans.selection_id", ondelete="CASCADE"),
        primary_key=True,
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    ordinal: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


_merged_metadata_lock = Lock()


def __getattr__(name: str) -> Any:
    """Build the cross-site DDL graph only for migration/module consumers.

    Ordinary readers and writers use Base.metadata and the mapped classes.
    Keep the existing exported object, with one construction even when several
    threads first request it together. Failed construction remains retryable.
    """
    if name != "merged_metadata":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _merged_metadata_lock:
        if name not in globals():
            from ultima_scraper_db_archive import execution_models, plugin_models, favourites_models  # noqa: F401
            globals()[name] = create_merged_metadata(Base)
        return globals()[name]


def __dir__() -> list[str]:
    return sorted(set(globals()) | {"merged_metadata"})

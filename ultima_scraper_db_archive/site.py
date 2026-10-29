"""Simplified SQLModel schemas retained for archive migration compatibility."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from sqlmodel import Field  # type: ignore[attr-defined]
from sqlmodel import (
    BigInteger,
    SmallInteger,
    SQLModel,
    UniqueConstraint,
)


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp compatible with sqlite."""

    return datetime.now(timezone.utc)


class SiteTemplate(SQLModel):
    """Base class for site-specific database models."""

    __abstract__ = True


# This legacy source filename is intentionally stable for migration discovery.
DEFAULT_DB_PATH = Path.home() / ".ultima_scraper" / "ultima_scraper_mini.db"


class UserModel(SiteTemplate, table=True):
    """Lightweight representation of a scraper user for sqlite viewers."""

    __tablename__ = "users"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    username: str | None = Field(default=None, index=True)
    balance: float = Field(default=0.0)
    spend: bool = Field(default=False)
    performer: bool = Field(default=False)
    favorite: bool = Field(default=False)
    active: bool = Field(default=True)
    downloaded_at: datetime | None = Field(default=None)
    last_checked_at: datetime | None = Field(default=None)
    join_date: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime | None = Field(default=None)

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to the current UTC time."""

        self.updated_at = utcnow()

    @property
    def is_active(self) -> bool:
        """Flag indicating if the account is active and not archived."""

        return bool(self.active)


class UserAuthModel(SiteTemplate, table=True):
    """Stored authentication details for user accounts."""

    __tablename__ = "user_auths"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("cookie", "authorization", name="uq_user_auths_cookie_auth"),
    )

    id: int = Field(primary_key=True)
    site: str = Field(index=True)
    username: str | None = Field(default=None, index=True)
    user_id: int = Field(foreign_key="users.id", sa_type=BigInteger)
    cookie: str | None = Field(default=None)
    x_bc: str | None = Field(default=None)
    authorization: str | None = Field(default=None)
    user_agent: str
    email: str | None = Field(default=None)
    password: str | None = Field(default=None)
    status: str = Field(default="unknown")
    last_tested_at: datetime | None = Field(default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime | None = Field(default=None)

    def touch(self) -> None:
        """Update modification timestamp."""

        self.updated_at = utcnow()


class UserInfoModel(SiteTemplate, table=True):
    """User profile information and statistics."""

    __tablename__ = "user_infos"  # type: ignore[assignment]

    id: int = Field(primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        unique=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    name: str | None = Field(default=None)
    price: float = Field(default=0.0)
    description: str | None = Field(default=None)
    promotion: bool = Field(default=False)
    sex: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    gender: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    profile_type: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    sexual_content: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    partner_sex: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    partner_gender: int | None = Field(default=None, index=True, sa_type=SmallInteger)
    post_count: int = Field(default=0)
    media_count: int = Field(default=0)
    image_count: int = Field(default=0)
    video_count: int = Field(default=0)
    audio_count: int = Field(default=0)
    stream_count: int = Field(default=0)
    archived_post_count: int = Field(default=0)
    private_archived_post_count: int = Field(default=0)
    favourited_count: int = Field(default=0)
    favourites_count: int = Field(default=0)
    subscribers_count: int = Field(default=0)
    size: int = Field(default=0)
    location: str | None = Field(default=None)
    website: str | None = Field(default=None)
    downloaded_at: datetime | None = Field(default=None)
    first_downloaded_at: datetime | None = Field(default=None)
    uploaded_at: datetime | None = Field(default=None)


class SubscriptionModel(SiteTemplate, table=True):
    """User subscription relationships."""

    __tablename__ = "subscriptions"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            "user_id", "subscriber_id", name="uq_subscriptions_user_subscriber"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    subscriber_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    paid_content: bool = Field(default=False)
    active: bool = Field(default=True)
    downloaded_at: datetime | None = Field(default=None)
    expires_at: datetime = Field()
    renewed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class MediaModel(SiteTemplate, table=True):
    """Media files associated with content."""

    __tablename__ = "media"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    user_id: int = Field(
        foreign_key="users.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    url: str | None = Field(default=None)
    size: int = Field(default=0)
    category: str | None = Field(default=None)
    preview: bool = Field(default=False)
    created_at: datetime | None = Field(default=None)


class ContentMediaAssoModel(SiteTemplate, table=True):
    """Association table linking content to media."""

    __tablename__ = "content_media_asso"  # type: ignore[assignment]
    __table_args__ = (
        # Ensure each media item is linked only once per content item
        UniqueConstraint("story_id", "media_id", name="uq_content_media_story_media"),
        UniqueConstraint("post_id", "media_id", name="uq_content_media_post_media"),
        UniqueConstraint(
            "message_id", "media_id", name="uq_content_media_message_media"
        ),
        UniqueConstraint(
            "mass_message_id", "media_id", name="uq_content_media_mass_message_media"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    story_id: int | None = Field(
        default=None,
        foreign_key="x_stories.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    post_id: int | None = Field(
        default=None,
        foreign_key="x_posts.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    message_id: int | None = Field(
        default=None,
        foreign_key="x_messages.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    mass_message_id: int | None = Field(
        default=None,
        foreign_key="x_mass_messages.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    media_id: int = Field(
        foreign_key="media.id",
        index=True,
        sa_type=BigInteger,
        ondelete="CASCADE",
    )


class StoryModel(SiteTemplate, table=True):
    """Story content from user timeline."""

    __tablename__ = "x_stories"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    user_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    created_at: datetime = Field()


class PostModel(SiteTemplate, table=True):
    """Post content from user timeline."""

    __tablename__ = "x_posts"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    user_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    text: str | None = Field(default=None, index=True)
    price: float = Field(default=0.0)
    deleted: bool = Field(default=False)
    archived: bool = Field(default=False)
    paid: bool | None = Field(default=None)
    media_count: int = Field(default=0)
    created_at: datetime = Field()


class MessageModel(SiteTemplate, table=True):
    """Direct message content."""

    __tablename__ = "x_messages"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    user_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    receiver_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    queue_id: int | None = Field(
        default=None,
        foreign_key="x_mass_messages.id",
        sa_type=BigInteger,
        ondelete="SET NULL",
    )
    text: str | None = Field(default=None, index=True)
    price: float = Field(default=0.0)
    deleted: bool = Field(default=False)
    paid: bool | None = Field(default=None)
    verified: bool = Field(default=False)
    media_count: int = Field(default=0)
    created_at: datetime = Field()


class MassMessageModel(SiteTemplate, table=True):
    """Mass message content sent to multiple users."""

    __tablename__ = "x_mass_messages"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    user_id: int = Field(
        foreign_key="users.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    text: str | None = Field(default=None)
    price: float = Field(default=0.0)
    media_count: int = Field(default=0)
    expires_at: datetime = Field()
    created_at: datetime = Field()


class CommentModel(SiteTemplate, table=True):
    """Comments on posts."""

    __tablename__ = "comments"  # type: ignore[assignment]

    id: int = Field(primary_key=True, sa_type=BigInteger)
    post_id: int = Field(
        foreign_key="x_posts.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    reply_id: int | None = Field(
        default=None,
        foreign_key="comments.id",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    user_id: int = Field(sa_type=BigInteger)
    giphy_id: str | None = Field(default=None)
    text: str | None = Field(default=None)
    likes_count: int = Field(default=0)
    created_at: datetime = Field()


class JobModel(SiteTemplate, table=True):
    """Persisted job queue entries for historical inspection within the TUI."""

    __tablename__ = "jobs"  # type: ignore[assignment]

    job_id: str = Field(primary_key=True, max_length=64)
    job_type: str = Field(max_length=64, index=True)
    site: str = Field(max_length=64, index=True)
    status: str = Field(default="pending", max_length=32, index=True)
    priority: int = Field(default=0)
    worker_id: str | None = Field(default=None, max_length=64, index=True)
    retries: int = Field(default=0)
    max_retries: int = Field(default=3)
    args_json: str = Field(default="{}")
    auth_json: str | None = Field(default=None)
    user_auth_id: int | None = Field(
        default=None,
        foreign_key="user_auths.id",
        ondelete="SET NULL",
    )
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    last_event_at: datetime | None = Field(default=None)
    result_success: bool | None = Field(default=None)
    result_message: str | None = Field(default=None)
    result_error: str | None = Field(default=None)
    result_data_json: str | None = Field(default=None)
    result_completed_at: datetime | None = Field(default=None)

    JSON_EMPTY: ClassVar[str] = "{}"

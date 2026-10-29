"""add_daily_statistics_snapshots

Revision ID: b1f0f249d551
Revises: 86b0f35fafff
Create Date: 2026-03-08 11:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1f0f249d551"
down_revision: Union[str, Sequence[str], None] = "86b0f35fafff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SITE_SCHEMAS: tuple[str, ...] = ("onlyfans", "fansly", "loyalfans")


def upgrade() -> None:
    """Upgrade schema."""
    for schema in SITE_SCHEMAS:
        op.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.statistics (
                    id BIGSERIAL PRIMARY KEY,
                    bucket_date DATE NOT NULL,
                    bucket_started_at TIMESTAMPTZ NOT NULL,
                    bucket_ends_at TIMESTAMPTZ NOT NULL,
                    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    total_media_count BIGINT NOT NULL DEFAULT 0,
                    sized_media_count BIGINT NOT NULL DEFAULT 0,
                    zero_size_media_count BIGINT NOT NULL DEFAULT 0,
                    image_media_count BIGINT NOT NULL DEFAULT 0,
                    image_sized_count BIGINT NOT NULL DEFAULT 0,
                    video_media_count BIGINT NOT NULL DEFAULT 0,
                    video_sized_count BIGINT NOT NULL DEFAULT 0,
                    audio_media_count BIGINT NOT NULL DEFAULT 0,
                    audio_sized_count BIGINT NOT NULL DEFAULT 0,
                    other_media_count BIGINT NOT NULL DEFAULT 0,
                    other_sized_count BIGINT NOT NULL DEFAULT 0,
                    total_known_bytes BIGINT NOT NULL DEFAULT 0,
                    avg_media_size_bytes BIGINT NOT NULL DEFAULT 0,
                    avg_image_size_bytes BIGINT NOT NULL DEFAULT 0,
                    avg_video_size_bytes BIGINT NOT NULL DEFAULT 0,
                    avg_audio_size_bytes BIGINT NOT NULL DEFAULT 0,
                    avg_other_size_bytes BIGINT NOT NULL DEFAULT 0,
                    size_coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
                    CONSTRAINT uq_statistics_bucket_date UNIQUE (bucket_date)
                )
                """
            )
        )
        op.execute(
            sa.text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_statistics_bucket_date "
                f"ON {schema}.statistics (bucket_date)"
            )
        )
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS idx_statistics_calculated_at "
                f"ON {schema}.statistics (calculated_at)"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    for schema in SITE_SCHEMAS:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {schema}.idx_statistics_calculated_at"))
        op.execute(sa.text(f"DROP INDEX IF EXISTS {schema}.idx_statistics_bucket_date"))
        op.execute(sa.text(f"DROP TABLE IF EXISTS {schema}.statistics"))

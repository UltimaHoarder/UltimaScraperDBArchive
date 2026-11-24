"""Keep what a hosted front end's jobs scraped and downloaded, and budget them.

All four tables are in ``management`` and start empty:

- ``job_media_records``: one per job whose media are kept for a front end, with
  when the front end acknowledged it (``acked_at``).
- ``job_media_access``: each media the job's scrape returned to its account,
  per content it was in. ``seq`` is drawn again whenever a row is added or its
  media's download state changes, so a reader can page by it while the job
  runs.
- ``job_media_attribution``: media the job's download first put on disk, with
  the bytes written.
- ``job_download_budgets``: the bytes of new media a job may still download,
  shared by every download task of the job.

Job deletion leaves the first three alone; the terminal-job reconciler prunes
them once acknowledged and the job is gone, or after 30 days.

Revision ID: e4a7c2f9b315
Revises: c7d2e4f6a8b1
Create Date: 2026-11-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a7c2f9b315"
down_revision: Union[str, Sequence[str], None] = "c7d2e4f6a8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "management"
SEQUENCE = "job_media_access_seq"


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.create_table(
        "job_media_records",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_now()),
        sa.Column("acked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.execute(sa.schema.CreateSequence(sa.Sequence(SEQUENCE, schema=SCHEMA)))
    op.create_table(
        "job_media_access",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("site", sa.String(length=64), primary_key=True),
        sa.Column("media_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("content_type", sa.String(length=32), primary_key=True),
        sa.Column("content_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("performer_id", sa.BigInteger(), nullable=True),
        sa.Column("auth_user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_now()),
        sa.Column(
            "seq",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text(f"nextval('{SCHEMA}.{SEQUENCE}'::regclass)"),
        ),
        schema=SCHEMA,
    )
    op.execute(f"ALTER SEQUENCE {SCHEMA}.{SEQUENCE} OWNED BY {SCHEMA}.job_media_access.seq")
    op.create_index(
        "idx_job_media_access_job_seq", "job_media_access", ["job_id", "seq"], schema=SCHEMA
    )
    op.create_index(
        "idx_job_media_access_site_media", "job_media_access", ["site", "media_id"], schema=SCHEMA
    )
    op.create_table(
        "job_media_attribution",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("site", sa.String(length=64), primary_key=True),
        sa.Column("media_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("auth_user_id", sa.BigInteger(), nullable=True),
        sa.Column("bytes_on_disk", sa.BigInteger(), nullable=False),
        sa.Column("downloaded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_now()),
        schema=SCHEMA,
    )
    op.create_table(
        "job_download_budgets",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("budget_bytes", sa.BigInteger(), nullable=False),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.drop_table("job_download_budgets", schema=SCHEMA)
    op.drop_table("job_media_attribution", schema=SCHEMA)
    # The sequence is owned by job_media_access.seq and goes with the table.
    op.drop_table("job_media_access", schema=SCHEMA)
    op.drop_table("job_media_records", schema=SCHEMA)

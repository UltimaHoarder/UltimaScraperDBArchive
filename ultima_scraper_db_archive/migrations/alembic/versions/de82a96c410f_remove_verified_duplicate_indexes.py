"""Remove only catalog-verified duplicate nonunique indexes.

This migration needs an online PostgreSQL connection for dependency checks.
It uses ordinary transactional DDL, so deployment must allow table locks.
Unexpected definitions or dependencies abort the transaction before activation.
"""

from alembic import op
import sqlalchemy as sa

revision = "de82a96c410f"
down_revision = "c79e2b4a185d"
branch_labels = None
depends_on = None

SITE_PAIRS = (
    ("users", "username", "idx_users_username"),
    ("user_auths", "username", "idx_user_auths_username"),
    ("user_auths", "site", "idx_user_auths_site"),
    ("invalid_users", "user_id", "idx_invalid_users_user_id"),
    ("invalid_users", "site", "idx_invalid_users_site"),
    ("socials", "user_id", "idx_socials_user_id"),
    ("websites", "user_id", "idx_websites_user_id"),
    ("user_profile_media", "user_id", "idx_user_profile_media_user_id"),
    ("user_profile_media", "created_at", "idx_user_profile_media_created_at"),
    ("media", "user_id", "idx_media_user_id"),
    ("media_urls", "media_id", "idx_media_urls_media_id"),
    ("media_urls", "auth_id", "idx_media_urls_auth_id"),
    ("drm_manifest", "media_id", "idx_drm_manifest_media_id"),
    ("content_media_asso", "story_id", "ix_content_media_story_id"),
    ("content_media_asso", "message_id", "ix_content_media_message_id"),
    ("content_media_asso", "post_id", "ix_content_media_post_id"),
    ("content_media_asso", "mass_message_id", "ix_content_media_mass_message_id"),
    ("content_media_asso", "media_id", "ix_content_media_media_id"),
    ("mass_message_stats", "user_id", "idx_mass_message_stats_user_id"),
    ("websocket_messages", "site_account_user_id", "idx_websocket_messages_user_id"),
    ("filepaths", "media_id", "idx_filepaths_media_id"),
    ("remote_urls", "user_id", "idx_remote_urls_user_id"),
    ("bought_content", "buyer_id", "idx_bought_content_buyer_id"),
    ("bought_content", "supplier_id", "idx_bought_content_supplier_id"),
    ("histo_user_infos", "user_id", "idx_histo_user_infos_user_id"),
    ("linked_posts", "post_id", "idx_linked_posts_post_id"),
    ("linked_posts", "linked_post_id", "idx_linked_posts_linked_post_id"),
    ("linked_users", "linked_user_id", "idx_linked_users_linked_user_id"),
    ("linked_users", "post_id", "idx_linked_users_post_id"),
)

MANAGEMENT_PAIRS = (
    ("orders", "site_id", "idx_orders_site_id"),
    ("ordered_performers", "order_id", "idx_ordered_performers_order_id"),
    ("ordered_performers", "user_id", "idx_ordered_performers_user_id"),
    ("ordered_performers", "site_id", "idx_ordered_performers_site_id"),
    ("ordered_ppv", "order_id", "idx_ordered_ppv_order_id"),
    ("ordered_ppv", "user_id", "idx_ordered_ppv_user_id"),
    ("ordered_ppv", "site_id", "idx_ordered_ppv_site_id"),
)

_INDEX_INFO = sa.text("""
SELECT c.oid AS oid, n.nspname AS schema_name, t.relname AS table_name,
       i.indrelid AS table_oid, pg_get_indexdef(c.oid) AS definition,
       pg_get_indexdef(c.oid, 1, true) AS first_column,
       jsonb_build_array(
         c.relam, c.reltablespace, c.reloptions, c.relpersistence, c.relowner,
         i.indnatts, i.indnkeyatts, i.indisunique, i.indnullsnotdistinct,
         i.indimmediate, i.indkey::text, i.indcollation::text,
         i.indclass::text, i.indoption::text,
         i.indexprs::text, i.indpred::text,
         (SELECT jsonb_agg(jsonb_build_array(a.attstattarget, a.attoptions)
                           ORDER BY a.attnum)
          FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0)
       ) AS signature,
       (c.relkind = 'i' AND am.amname = 'btree'
        AND i.indnatts = 1 AND i.indnkeyatts = 1
        AND NOT i.indisunique AND NOT i.indisprimary AND NOT i.indisexclusion
        AND i.indexprs IS NULL AND i.indpred IS NULL
        AND i.indisvalid AND i.indisready AND i.indislive
        AND NOT i.indcheckxmin) AS usable,
       (i.indisclustered OR i.indisreplident
        OR obj_description(c.oid, 'pg_class') IS NOT NULL
        OR EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid = c.oid)
        OR EXISTS (SELECT 1 FROM pg_depend d
                   WHERE d.refclassid = 'pg_class'::regclass AND d.refobjid = c.oid)
        OR EXISTS (SELECT 1 FROM pg_depend d
                   WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid
                     AND d.deptype IN ('i', 'e', 'x', 'P', 'S'))
       ) AS protected
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_am am ON am.oid = c.relam
WHERE n.nspname = :schema AND c.relname = :name
""")


def _read_index(connection, schema, name):
    return (
        connection.execute(_INDEX_INFO, {"schema": schema, "name": name})
        .mappings()
        .one_or_none()
    )


def _qualified(connection, schema, name):
    quote = connection.dialect.identifier_preparer.quote_identifier
    return f"{quote(schema)}.{quote(name)}"


def candidate_pairs():
    for schema in ("fansly", "loyalfans", "onlyfans"):
        for table, column, keep in SITE_PAIRS:
            # Alembic's merged schema and older direct create_all used these
            # two names. Only known names are candidates; no catalog-wide drop.
            for drop in (f"ix_{schema}_{table}_{column}", f"ix_{table}_{column}"):
                yield schema, table, column, keep, drop
    for table, column, keep in MANAGEMENT_PAIRS:
        yield "management", table, column, keep, f"ix_management_{table}_{column}"


def _retained_index(connection, schema, table, column, keep):
    info = _read_index(connection, schema, keep)
    if (
        info is None
        or info["table_name"] != table
        or info["first_column"] != column
        or not info["usable"]
    ):
        raise RuntimeError(
            f"Duplicate-index migration cannot verify retained {schema}.{keep}"
        )
    return info


def upgrade():
    connection = op.get_bind()
    for schema, table, column, keep, drop in candidate_pairs():
        duplicate = _read_index(connection, schema, drop)
        if duplicate is None:
            continue
        if duplicate["table_name"] != table:
            raise RuntimeError(
                f"Unexpected table for duplicate-index candidate {schema}.{drop}"
            )
        # Prevent DDL changing the retained definition/dependencies between the
        # catalog verification and DROP. Existing session lock_timeout applies.
        connection.execute(
            sa.text(
                f"LOCK TABLE {_qualified(connection, schema, table)} IN ACCESS EXCLUSIVE MODE"
            )
        )
        duplicate = _read_index(connection, schema, drop)
        if duplicate is None:
            continue
        retained = _retained_index(connection, schema, table, column, keep)
        if (
            not duplicate["usable"]
            or duplicate["protected"]
            or duplicate["table_oid"] != retained["table_oid"]
            or duplicate["signature"] != retained["signature"]
        ):
            raise RuntimeError(
                f"Refusing to remove {schema}.{drop}: definition or dependencies require review"
            )
        connection.execute(
            sa.text(f"DROP INDEX {_qualified(connection, schema, drop)} RESTRICT")
        )


def downgrade():
    connection = op.get_bind()
    for schema, table, column, keep, drop in candidate_pairs():
        # Restore the original Alembic names, not obsolete create_all aliases.
        if schema != "management" and drop == f"ix_{table}_{column}":
            continue
        if _read_index(connection, schema, drop) is not None:
            continue
        if _read_index(connection, schema, keep) is None:
            continue
        connection.execute(
            sa.text(
                f"LOCK TABLE {_qualified(connection, schema, table)} IN ACCESS EXCLUSIVE MODE"
            )
        )
        retained = _retained_index(connection, schema, table, column, keep)
        if _read_index(connection, schema, drop) is not None:
            continue
        # Copy the retained catalog definition, including its storage options.
        definition = retained["definition"].split(" ON ", 1)[1]
        quote = connection.dialect.identifier_preparer.quote_identifier
        connection.execute(sa.text(f"CREATE INDEX {quote(drop)} ON {definition}"))

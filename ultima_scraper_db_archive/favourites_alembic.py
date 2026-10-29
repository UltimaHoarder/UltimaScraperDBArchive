"""Favourites-specific comparisons for archive Alembic previews."""

import re

from sqlalchemy import text


_FAVOURITES_NEXTVAL = re.compile(
    r"\s*nextval\(\s*'(?:\"?management\"?\.)?\"?favourites_id_seq\"?'"
    r"(?:\s*::\s*(?:pg_catalog\.)?regclass)?\s*\)\s*", re.IGNORECASE
)


def compare_favourites_server_default(
    context, inspected_column, metadata_column, inspected_default,
    metadata_default, rendered_metadata_default,
) -> bool | None:
    """Compare the owned partitioned ID sequence without calling nextval.

    Alembic treats an owned sequence as SERIAL and removes its reflected
    default. Its ordinary SERIAL exemption does not apply to our composite
    primary key, so inspect the real expression and sequence dependency.
    """
    table = metadata_column.table
    if (table.schema, table.name, metadata_column.name) != ('management', 'favourites', 'id'):
        return None
    actual = context.connection.execute(text("""
        SELECT pg_get_expr(d.adbin,d.adrelid) AS expression,
               EXISTS (SELECT 1 FROM pg_depend p
                   WHERE p.classid='pg_attrdef'::regclass AND p.objid=d.oid
                     AND p.refclassid='pg_class'::regclass
                     AND p.refobjid=to_regclass('management.favourites_id_seq')) AS expected_sequence
        FROM pg_attrdef d JOIN pg_attribute a
          ON (a.attrelid,a.attnum)=(d.adrelid,d.adnum)
        WHERE d.adrelid=to_regclass('management.favourites') AND a.attname='id'
    """)).mappings().first()
    expression = actual['expression'] if actual else None
    if not _FAVOURITES_NEXTVAL.fullmatch(rendered_metadata_default or ''):
        return expression != rendered_metadata_default
    return not (actual and actual['expected_sequence']
                and _FAVOURITES_NEXTVAL.fullmatch(expression or ''))



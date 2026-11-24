"""Server-default comparisons for archive Alembic previews.

Alembic treats a column whose default draws from a sequence the column owns as
SERIAL and drops that default when it reflects the table. Its usual SERIAL
exemption doesn't apply to our columns (a composite primary key, or a plain
BIGINT that isn't the key), so every preview would otherwise offer to add the
default again. For the columns listed here the real expression and sequence
dependency are read from the catalog instead, without calling nextval.
"""

import re

from sqlalchemy import text

# (schema, table, column) -> the sequence its default must draw from.
OWNED_SEQUENCE_DEFAULTS = {
    ("management", "favourites", "id"): "favourites_id_seq",
    ("management", "job_media_access", "seq"): "job_media_access_seq",
}


def _nextval(schema: str, sequence: str) -> re.Pattern[str]:
    return re.compile(
        rf"\s*nextval\(\s*'(?:\"?{re.escape(schema)}\"?\.)?\"?{re.escape(sequence)}\"?'"
        r"(?:\s*::\s*(?:pg_catalog\.)?regclass)?\s*\)\s*",
        re.IGNORECASE,
    )


_NEXTVAL = {key: _nextval(key[0], sequence) for key, sequence in OWNED_SEQUENCE_DEFAULTS.items()}
# Kept for callers of the favourites-only version.
_FAVOURITES_NEXTVAL = _NEXTVAL[("management", "favourites", "id")]


def compare_owned_sequence_default(
    context, inspected_column, metadata_column, inspected_default,
    metadata_default, rendered_metadata_default,
) -> bool | None:
    """True when the default differs; None leaves other columns to Alembic."""
    table = metadata_column.table
    key = (table.schema, table.name, metadata_column.name)
    sequence = OWNED_SEQUENCE_DEFAULTS.get(key)
    if sequence is None:
        return None
    schema, table_name, column = key
    actual = context.connection.execute(
        text("""
        SELECT pg_get_expr(d.adbin,d.adrelid) AS expression,
               EXISTS (SELECT 1 FROM pg_depend p
                   WHERE p.classid='pg_attrdef'::regclass AND p.objid=d.oid
                     AND p.refclassid='pg_class'::regclass
                     AND p.refobjid=to_regclass(:sequence)) AS expected_sequence
        FROM pg_attrdef d JOIN pg_attribute a
          ON (a.attrelid,a.attnum)=(d.adrelid,d.adnum)
        WHERE d.adrelid=to_regclass(:table) AND a.attname=:column
        """),
        {"sequence": f"{schema}.{sequence}", "table": f"{schema}.{table_name}", "column": column},
    ).mappings().first()
    expression = actual["expression"] if actual else None
    pattern = _NEXTVAL[key]
    if not pattern.fullmatch(rendered_metadata_default or ""):
        return expression != rendered_metadata_default
    return not (actual and actual["expected_sequence"] and pattern.fullmatch(expression or ""))


# The name env.py and older callers use.
compare_favourites_server_default = compare_owned_sequence_default

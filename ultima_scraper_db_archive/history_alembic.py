"""Keep runtime job-history partition leaves out of Alembic autogeneration."""

HISTORY_PARENTS = (
    "execution_mutations",
    "execution_attempts",
    "execution_outbox",
    "job_tasks",
)
_HEX = frozenset("0123456789abcdef")


def is_runtime_history_leaf(name: str | None) -> bool:
    """Per-job and legacy leaves, managed by explicit partition lifecycle."""
    name = name or ""
    for parent in HISTORY_PARENTS:
        if name == parent + "_legacy":
            return True
        prefix = parent + "_job_"
        suffix = name[len(prefix):]
        if name.startswith(prefix) and len(suffix) == 32 and set(suffix) <= _HEX:
            return True
    return False


def is_transient_concurrent_index(name: str | None) -> bool:
    """PostgreSQL concurrent reindex / create index transient names."""
    if not name:
        return False
    return name.endswith("_ccnew") or name.endswith("_ccold")


def include_name(name: str | None, type_: str, parent_names) -> bool:
    """Skip runtime leaves by name, before Alembic reflects them.

    Job deletion and history retirement drop leaves at any time. include_object
    only sees tables after reflection, so a leaf dropped between Alembic listing
    the schema's tables and reflecting it would fail the comparison.
    """
    if type_ == "table" and parent_names.get("schema_name") == "management":
        return not is_runtime_history_leaf(name)
    if type_ == "index" and is_transient_concurrent_index(name):
        return False
    return True


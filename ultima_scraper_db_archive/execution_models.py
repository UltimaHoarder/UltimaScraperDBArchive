"""Durable execution state; Redis projections are never ownership evidence."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    case,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .databases.ultima_archive.schemas.templates.postgres_site import (
    TIMESTAMPTZ,
    ManagementTemplate,
)


class ExecutionDefinitionModel(ManagementTemplate):
    __tablename__ = "execution_definitions"
    __table_args__ = ({"schema": "management"},)
    definition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class ExecutionRunModel(ManagementTemplate):
    __tablename__ = "execution_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["definition_id", "revision"],
            [
                "management.execution_definitions.definition_id",
                "management.execution_definitions.revision",
            ],
        ),
        CheckConstraint(
            "state IN ('pending','running','paused','completed','failed','cancelled')",
            name="ck_execution_run_state",
        ),
        Index("idx_execution_runs_active", "state", "next_at", "last_admitted_at"),
        {"schema": "management"},
    )
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), server_default="pending")
    backend_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, server_default="0")
    config_json: Mapped[str] = mapped_column(Text)
    next_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    last_admitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)


class ExecutionWorkModel(ManagementTemplate):
    """Narrow ownership/lease rows for the bounded resident window."""

    __tablename__ = "execution_work"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','running','persisting','completed','failed','cancelled')",
            name="ck_execution_work_state",
        ),
        CheckConstraint(
            "payload_bytes >= 0 AND attempt >= 0", name="ck_execution_work_budget"
        ),
        Index(
            "idx_execution_work_ready",
            "lane",
            "available_at",
            "run_id",
            postgresql_where=text("state = 'queued'"),
        ),
        Index(
            "idx_execution_work_expired",
            "lease_until",
            postgresql_where=text("state IN ('running','persisting')"),
        ),
        Index(
            "idx_execution_work_claim_order",
            "run_id",
            "created_at",
            "task_id",
            postgresql_where=text("state = 'queued'"),
        ),
        Index(
            "idx_execution_work_terminal",
            "run_id",
            "task_id",
            postgresql_where=text("state IN ('completed','failed')"),
            postgresql_include=["payload_size"],
        ),
        {"schema": "management"},
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("management.execution_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), server_default="queued")
    lane: Mapped[str] = mapped_column(String(16))
    site: Mapped[str] = mapped_column(String(64))
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text))
    dedup_key: Mapped[str] = mapped_column(Text)
    payload_bytes: Mapped[int] = mapped_column(BigInteger)
    payload_size: Mapped[int] = mapped_column(BigInteger)
    candidate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, server_default="0")
    token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    payload_record: Mapped["ExecutionWorkPayloadModel"] = relationship(
        # Load only after the ownership rows have been locked. Joining the
        # payload into SELECT FOR UPDATE could lock it before its queue row,
        # reversing the lifecycle transaction's work -> payload lock order.
        lazy="selectin",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @hybrid_property
    def payload_json(self) -> str:
        return self.payload_record.payload_json

    @payload_json.inplace.setter
    def _set_payload_json(self, value: str) -> None:
        if self.payload_record is None:
            self.payload_record = ExecutionWorkPayloadModel(payload_json=value)
        else:
            self.payload_record.payload_json = value
        self.payload_size = len(value.encode("utf-8"))

    @payload_json.inplace.expression
    @classmethod
    def _payload_json_expression(cls):
        payload = (
            select(ExecutionWorkPayloadModel.payload_json)
            .where(
                ExecutionWorkPayloadModel.run_id == cls.run_id,
                ExecutionWorkPayloadModel.task_id == cls.task_id,
            )
            .correlate_except(ExecutionWorkPayloadModel)
            .scalar_subquery()
        )
        # Anchor standalone select(payload_json) to one ownership row too;
        # otherwise SQLAlchemy places both tables inside the scalar subquery.
        return case((cls.run_id.is_not(None), payload))


class ExecutionWorkPayloadModel(ManagementTemplate):
    """Payload versions are never scanned to count or claim resident work."""

    __tablename__ = "execution_work_payloads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["management.execution_work.run_id", "management.execution_work.task_id"],
            ondelete="CASCADE",
        ),
        {"schema": "management"},
    )
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ExecutionAttemptModel(ManagementTemplate):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "token", name="uq_execution_attempt_token"),
        Index("idx_execution_attempts_run", "run_id", "started_at"),
        {"schema": "management", "postgresql_partition_by": "LIST (run_id)"},
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("management.execution_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    timings_json: Mapped[str] = mapped_column(Text, server_default="{}")


class ExecutionResourceModel(ManagementTemplate):
    __tablename__ = "execution_resources"
    __table_args__ = (Index("idx_execution_resources_run", "run_id"), {"schema": "management"})
    resource_key: Mapped[str] = mapped_column(Text, primary_key=True)
    token: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("management.execution_runs.run_id", ondelete="CASCADE")
    )
    task_id: Mapped[str] = mapped_column(String(64))
    lease_until: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


class ExecutionOutboxModel(ManagementTemplate):
    __tablename__ = "execution_outbox"
    __table_args__ = (
        Index(
            "idx_execution_outbox_pending",
            "event_id",
            postgresql_where=text("delivered = false"),
        ),
        Index("idx_execution_outbox_run", "run_id", "event_id"),
        # Event replay reads a global sequence range across every run.
        Index("idx_execution_outbox_sequence", "sequence"),
        UniqueConstraint("run_id", "sequence", name="uq_execution_outbox_sequence"),
        {"schema": "management", "postgresql_partition_by": "LIST (run_id)"},
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("management.execution_runs.run_id", ondelete="CASCADE"), primary_key=True
    )
    payload_json: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class ExecutionMutationModel(ManagementTemplate):
    """Map a logical task mutation to its committed writer receipt."""

    __tablename__ = "execution_mutations"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "task_id", "mutation_key", name="execution_mutations_partitioned_pkey"),
        Index("idx_execution_mutations_command", "command_id"),
        {"schema": "management", "postgresql_partition_by": "LIST (run_id)"},
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("management.execution_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mutation_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    command_id: Mapped[str] = mapped_column(String(128))


class ExecutionFeedModel(ManagementTemplate):
    """Sequence committed events in the relay, away from worker completion."""

    __tablename__ = "execution_feed"
    __table_args__ = ({"schema": "management"},)
    feed_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_sequence: Mapped[int] = mapped_column(BigInteger, server_default="1")


EXECUTION_MODELS = (
    ExecutionDefinitionModel,
    ExecutionRunModel,
    ExecutionWorkModel,
    ExecutionWorkPayloadModel,
    ExecutionAttemptModel,
    ExecutionResourceModel,
    ExecutionOutboxModel,
    ExecutionMutationModel,
    ExecutionFeedModel,
)


class ExecutionAttemptIdentityModel(ManagementTemplate):
    __tablename__ = "execution_attempt_identities"
    __table_args__ = (Index("idx_execution_attempt_identities_run", "run_id", "token"), {"schema": "management"})
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)


class ExecutionOutboxIdentityModel(ManagementTemplate):
    __tablename__ = "execution_outbox_identities"
    __table_args__ = (Index("idx_execution_outbox_identities_run", "run_id", "event_id"), UniqueConstraint("sequence", name="uq_execution_outbox_identity_sequence"), {"schema": "management"})
    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    run_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class JobTaskIdentityModel(ManagementTemplate):
    __tablename__ = "job_task_identities"
    __table_args__ = (Index("idx_job_task_identities_job", "job_id", "task_id"), {"schema": "management"})
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64))

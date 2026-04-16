"""SQLAlchemy ORM models for jenkins-log-sentinel."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TriggerType(str, enum.Enum):
    GERRIT = "GERRIT"
    UPSTREAM = "UPSTREAM"
    TIMER = "TIMER"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    FINDINGS = "FINDINGS"
    ERROR = "ERROR"


class DetectorType(str, enum.Enum):
    REGEX = "REGEX"
    TRUFFLEHOG = "TRUFFLEHOG"
    LLM = "LLM"


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class NotificationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SLACK = "SLACK"
    WEBHOOK = "WEBHOOK"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class JenkinsInstance(Base):
    __tablename__ = "jenkins_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    jobs_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    builds: Mapped[list[Build]] = relationship("Build", back_populates="jenkins_instance")
    scan_states: Mapped[list[ScanState]] = relationship(
        "ScanState", back_populates="jenkins_instance"
    )


class ScanState(Base):
    """Tracks the highest build number scanned per job per instance."""

    __tablename__ = "scan_state"
    __table_args__ = (
        UniqueConstraint("jenkins_instance_id", "job_name", name="uq_scan_state_instance_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jenkins_instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jenkins_instances.id", ondelete="CASCADE"), nullable=False
    )
    job_name: Mapped[str] = mapped_column(String(512), nullable=False)
    last_scanned_build_number: Mapped[int] = mapped_column(Integer, default=0)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jenkins_instance: Mapped[JenkinsInstance] = relationship(
        "JenkinsInstance", back_populates="scan_states"
    )


class Build(Base):
    __tablename__ = "builds"
    __table_args__ = (
        UniqueConstraint(
            "jenkins_instance_id", "job_name", "build_number", name="uq_build_instance_job_num"
        ),
        Index("ix_builds_job_name", "job_name"),
        Index("ix_builds_trigger_type", "trigger_type"),
        Index("ix_builds_triggered_by_email", "triggered_by_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jenkins_instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jenkins_instances.id", ondelete="CASCADE"), nullable=False
    )
    job_name: Mapped[str] = mapped_column(String(512), nullable=False)
    build_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Provenance
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType), default=TriggerType.UNKNOWN
    )
    # GERRIT fields
    gerrit_change_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gerrit_change_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gerrit_project: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gerrit_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gerrit_patchset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # UPSTREAM fields
    upstream_job: Mapped[str | None] = mapped_column(String(512), nullable=True)
    upstream_build_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # MANUAL / common
    triggered_by_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_by_email: Mapped[str | None] = mapped_column(String(512), nullable=True)

    build_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    log_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    scan_status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus), default=ScanStatus.PENDING
    )
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jenkins_instance: Mapped[JenkinsInstance] = relationship(
        "JenkinsInstance", back_populates="builds"
    )
    findings: Mapped[list[Finding]] = relationship("Finding", back_populates="build")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_build_id", "build_id"),
        Index("ix_findings_severity", "severity"),
        Index("ix_findings_finding_type", "finding_type"),
        Index("ix_findings_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("builds.id", ondelete="CASCADE"), nullable=False
    )

    detector: Mapped[DetectorType] = mapped_column(Enum(DetectorType), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)

    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ±5 lines of context with secret value replaced by REDACTED
    line_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. "AKI***...***XYZ"  — never the full value
    display_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # SHA256 of the normalized raw value
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Base64 encoding of the original candidate
    encoding: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # NULL | BASE64 | BASE64URL | JWT

    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    exemption_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exemptions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    build: Mapped[Build] = relationship("Build", back_populates="findings")
    exemption: Mapped[Exemption | None] = relationship("Exemption", back_populates="findings")
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="finding"
    )


class Exemption(Base):
    __tablename__ = "exemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL = match all instances
    jenkins_instance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jenkins_instances.id", ondelete="CASCADE"), nullable=True
    )
    # Supports % wildcard (SQL LIKE). NULL = match all jobs.
    job_name_pattern: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # NULL = match all finding types
    finding_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # SHA256 of specific value. NULL = match by type/job only (broad exemption).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    findings: Mapped[list[Finding]] = relationship("Finding", back_populates="exemption")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_finding_id", "finding_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel), nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus), default=NotificationStatus.PENDING
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    finding: Mapped[Finding] = relationship("Finding", back_populates="notifications")

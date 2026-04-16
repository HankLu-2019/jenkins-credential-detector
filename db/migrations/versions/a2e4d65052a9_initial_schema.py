"""initial_schema

Revision ID: a2e4d65052a9
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2e4d65052a9"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jenkins_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("jobs_path", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "scan_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "jenkins_instance_id",
            sa.Integer(),
            sa.ForeignKey("jenkins_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_name", sa.String(512), nullable=False),
        sa.Column("last_scanned_build_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "jenkins_instance_id", "job_name", name="uq_scan_state_instance_job"
        ),
    )

    trigger_type = sa.Enum(
        "GERRIT", "UPSTREAM", "TIMER", "MANUAL", "UNKNOWN", name="triggertype"
    )
    scan_status = sa.Enum("PENDING", "CLEAN", "FINDINGS", "ERROR", name="scanstatus")

    op.create_table(
        "builds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "jenkins_instance_id",
            sa.Integer(),
            sa.ForeignKey("jenkins_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_name", sa.String(512), nullable=False),
        sa.Column("build_number", sa.Integer(), nullable=False),
        sa.Column("trigger_type", trigger_type, nullable=False, server_default="UNKNOWN"),
        # Gerrit
        sa.Column("gerrit_change_id", sa.String(255), nullable=True),
        sa.Column("gerrit_change_number", sa.Integer(), nullable=True),
        sa.Column("gerrit_project", sa.String(512), nullable=True),
        sa.Column("gerrit_branch", sa.String(255), nullable=True),
        sa.Column("gerrit_patchset", sa.Integer(), nullable=True),
        # Upstream
        sa.Column("upstream_job", sa.String(512), nullable=True),
        sa.Column("upstream_build_number", sa.Integer(), nullable=True),
        # Manual/common
        sa.Column("triggered_by_user", sa.String(255), nullable=True),
        sa.Column("triggered_by_email", sa.String(512), nullable=True),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("log_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("scan_status", scan_status, nullable=False, server_default="PENDING"),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "jenkins_instance_id",
            "job_name",
            "build_number",
            name="uq_build_instance_job_num",
        ),
    )
    op.create_index("ix_builds_job_name", "builds", ["job_name"])
    op.create_index("ix_builds_trigger_type", "builds", ["trigger_type"])
    op.create_index("ix_builds_triggered_by_email", "builds", ["triggered_by_email"])

    op.create_table(
        "exemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "jenkins_instance_id",
            sa.Integer(),
            sa.ForeignKey("jenkins_instances.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("job_name_pattern", sa.String(512), nullable=True),
        sa.Column("finding_type", sa.String(128), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    detector_type = sa.Enum("REGEX", "TRUFFLEHOG", "LLM", name="detectortype")
    severity = sa.Enum("CRITICAL", "HIGH", "MEDIUM", "LOW", name="severity")

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "build_id",
            sa.Integer(),
            sa.ForeignKey("builds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("detector", detector_type, nullable=False),
        sa.Column("finding_type", sa.String(128), nullable=False),
        sa.Column("severity", severity, nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("line_context", sa.Text(), nullable=True),
        sa.Column("display_value", sa.String(512), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("encoding", sa.String(32), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("llm_explanation", sa.Text(), nullable=True),
        sa.Column(
            "exemption_id",
            sa.Integer(),
            sa.ForeignKey("exemptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_findings_build_id", "findings", ["build_id"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_finding_type", "findings", ["finding_type"])
    op.create_index("ix_findings_content_hash", "findings", ["content_hash"])

    notification_channel = sa.Enum(
        "EMAIL", "SLACK", "WEBHOOK", "OTHER", name="notificationchannel"
    )
    notification_status = sa.Enum(
        "PENDING", "SENT", "FAILED", "ACKNOWLEDGED", name="notificationstatus"
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", notification_channel, nullable=False),
        sa.Column("recipient", sa.String(512), nullable=False),
        sa.Column(
            "status", notification_status, nullable=False, server_default="PENDING"
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_finding_id", "notifications", ["finding_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("findings")
    op.drop_table("exemptions")
    op.drop_table("builds")
    op.drop_table("scan_state")
    op.drop_table("jenkins_instances")

    for enum_name in (
        "notificationstatus",
        "notificationchannel",
        "severity",
        "detectortype",
        "scanstatus",
        "triggertype",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

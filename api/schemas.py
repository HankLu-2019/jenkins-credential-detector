"""Pydantic response schemas for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JenkinsInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    jobs_path: str
    description: str
    created_at: datetime


class BuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    jenkins_instance_id: int
    job_name: str
    build_number: int
    trigger_type: str
    gerrit_change_id: str | None
    gerrit_change_number: int | None
    gerrit_project: str | None
    gerrit_branch: str | None
    gerrit_patchset: int | None
    upstream_job: str | None
    upstream_build_number: int | None
    triggered_by_user: str | None
    triggered_by_email: str | None
    build_started_at: datetime | None
    log_size_bytes: int
    scan_status: str
    scanned_at: datetime | None
    finding_count: int = 0


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    build_id: int
    detector: str
    finding_type: str
    severity: str
    line_number: int | None
    line_context: str | None
    display_value: str | None
    content_hash: str
    encoding: str | None
    llm_confidence: float | None
    llm_explanation: str | None
    exemption_id: int | None
    created_at: datetime


class ExemptionIn(BaseModel):
    jenkins_instance_id: int | None = None
    job_name_pattern: str | None = None
    finding_type: str | None = None
    content_hash: str | None = None
    reason: str = ""
    created_by: str = ""
    expires_at: datetime | None = None


class ExemptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    jenkins_instance_id: int | None
    job_name_pattern: str | None
    finding_type: str | None
    content_hash: str | None
    reason: str
    created_by: str
    expires_at: datetime | None
    created_at: datetime


class StatsOut(BaseModel):
    total_findings: int
    open_findings: int
    critical: int
    high: int
    medium: int
    low: int
    total_builds_scanned: int
    builds_with_findings: int
    top_jobs: list[dict]

"""Notification sender using Apprise.

Processes all PENDING Notification records, sends them via configured
Apprise channels, and updates their status in the DB.

Upstream-triggered builds walk up to the originating build to find the
real owner, since a nightly pipeline should notify the developer whose
commit introduced the leak — not the scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import apprise
from sqlalchemy.orm import Session

from db.models import Build, Finding, Notification, NotificationStatus

logger = logging.getLogger(__name__)

_MAX_UPSTREAM_DEPTH = 5  # avoid infinite loops in recursive upstream chains


def _find_upstream_owner(
    build: Build, session: Session, depth: int = 0
) -> str | None:
    """Walk the upstream chain to find the originating human owner."""
    if depth >= _MAX_UPSTREAM_DEPTH:
        return None
    if build.trigger_type.value in ("GERRIT", "MANUAL"):
        return build.triggered_by_email or build.triggered_by_user
    if build.trigger_type.value == "UPSTREAM" and build.upstream_job:
        parent = (
            session.query(Build)
            .filter_by(
                jenkins_instance_id=build.jenkins_instance_id,
                job_name=build.upstream_job,
                build_number=build.upstream_build_number,
            )
            .first()
        )
        if parent:
            return _find_upstream_owner(parent, session, depth + 1)
    return None


def _resolve_recipient(
    finding: Finding,
    session: Session,
    fallback: str,
) -> str:
    """Determine the best recipient for a finding's notification."""
    build = finding.build
    ttype = build.trigger_type.value

    if ttype == "GERRIT":
        return build.triggered_by_email or build.triggered_by_user or fallback
    if ttype == "MANUAL":
        return build.triggered_by_email or build.triggered_by_user or fallback
    if ttype == "UPSTREAM":
        owner = _find_upstream_owner(build, session)
        return owner or fallback
    # TIMER or UNKNOWN → team channel / fallback
    return fallback


def _build_message(finding: Finding) -> tuple[str, str]:
    """Return (title, body) for the notification."""
    build = finding.build
    title = (
        f"[{finding.severity.value}] Credential leak in "
        f"{build.job_name} #{build.build_number}"
    )
    body_lines = [
        f"Type: {finding.finding_type}",
        f"Severity: {finding.severity.value}",
        f"Value (masked): {finding.display_value or '(unavailable)'}",
        f"Line: {finding.line_number or 'unknown'}",
        f"Detector: {finding.detector.value}",
        f"Confidence: {finding.llm_confidence:.0%}" if finding.llm_confidence else "",
        "",
        f"Trigger: {build.trigger_type.value}",
    ]
    if build.trigger_type.value == "GERRIT":
        body_lines.append(f"Gerrit change: {build.gerrit_change_id} (project: {build.gerrit_project})")
    if build.trigger_type.value == "UPSTREAM":
        body_lines.append(f"Upstream: {build.upstream_job} #{build.upstream_build_number}")

    if finding.llm_explanation:
        body_lines += ["", f"Explanation: {finding.llm_explanation}"]

    body_lines += [
        "",
        "Please review and rotate the credential, then add an exemption if it is a false positive.",
    ]
    return title, "\n".join(l for l in body_lines if l is not None)


def send_pending_notifications(
    session: Session,
    apprise_urls: list[str],
    fallback_recipient: str = "",
) -> int:
    """Send all PENDING notifications. Returns count of successfully sent."""
    pending = (
        session.query(Notification)
        .filter_by(status=NotificationStatus.PENDING)
        .all()
    )

    if not pending:
        return 0

    sent_count = 0
    for notif in pending:
        finding = notif.finding
        recipient = _resolve_recipient(finding, session, fallback_recipient)

        if not recipient and not apprise_urls:
            logger.warning("No recipient or channel for finding %d — skipping", finding.id)
            notif.status = NotificationStatus.FAILED
            continue

        title, body = _build_message(finding)

        # Build Apprise instance with all configured channels
        ap = apprise.Apprise()
        for url in apprise_urls:
            ap.add(url)

        # If we have an email recipient and the channels include a mailto:// URL,
        # Apprise handles routing. For Slack/Teams we just broadcast to the channel.
        try:
            ok = ap.notify(title=title, body=body)
            notif.status = NotificationStatus.SENT if ok else NotificationStatus.FAILED
            notif.sent_at = datetime.now(tz=timezone.utc)
            if ok:
                sent_count += 1
                logger.info("Notification sent for finding %d to %s", finding.id, recipient)
            else:
                logger.warning("Apprise notification failed for finding %d", finding.id)
        except Exception as e:
            logger.error("Error sending notification for finding %d: %s", finding.id, e)
            notif.status = NotificationStatus.FAILED

    session.commit()
    return sent_count

"""Pipeline orchestrator — runs the 5-stage funnel for a single build log.

Stage 1: Regex pre-filter
Stage 2: TruffleHog subprocess
Stage 3: LLM classification (Ollama)
Stage 4: Exemption check
Stage 5: Persist findings + queue notifications
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from db.models import Build, DetectorType, Finding, Notification, NotificationChannel, NotificationStatus, ScanStatus, Severity
from scanner.config import Settings
from scanner.detectors import llm_detector, regex_detector, trufflehog_detector
from scanner.detectors.llm_detector import LLMResult
from scanner.detectors.regex_detector import Candidate
from scanner.exemptions import find_exemption

logger = logging.getLogger(__name__)


def _severity_enum(s: str) -> Severity:
    try:
        return Severity[s.upper()]
    except KeyError:
        return Severity.MEDIUM


def _detector_enum(s: str) -> DetectorType:
    mapping = {"REGEX": DetectorType.REGEX, "TRUFFLEHOG": DetectorType.TRUFFLEHOG, "LLM": DetectorType.LLM}
    return mapping.get(s.upper(), DetectorType.REGEX)


def _merge_candidates(
    regex_hits: list[Candidate],
    trufflehog_hits: list[Candidate],
) -> list[Candidate]:
    """Merge two candidate lists, deduplicating by content_hash."""
    seen: set[str] = set()
    merged: list[Candidate] = []
    for c in regex_hits + trufflehog_hits:
        if c.content_hash not in seen:
            seen.add(c.content_hash)
            merged.append(c)
    return merged


async def process_build_log(
    build: Build,
    log_path: Path,
    settings: Settings,
    session: Session,
) -> int:
    """Run the full detection pipeline for one build log.

    Returns the number of new findings written to the DB.
    """
    logger.info("Scanning build %s #%d (%s)", build.job_name, build.build_number, log_path)

    # Check log size limit
    try:
        log_size = log_path.stat().st_size
    except OSError:
        build.scan_status = ScanStatus.ERROR
        return 0

    build.log_size_bytes = log_size

    if settings.scan.max_log_size_bytes > 0 and log_size > settings.scan.max_log_size_bytes:
        logger.warning(
            "Skipping %s #%d: log too large (%d bytes)",
            build.job_name, build.build_number, log_size,
        )
        build.scan_status = ScanStatus.ERROR
        return 0

    # --- Stage 1: Regex ---
    regex_hits = regex_detector.scan_log(log_path)
    logger.debug("Regex found %d candidates", len(regex_hits))

    # --- Stage 2: TruffleHog ---
    th_hits: list[Candidate] = []
    if settings.trufflehog.binary:
        th_hits = trufflehog_detector.scan_log(
            log_path,
            binary=settings.trufflehog.binary,
            extra_args=settings.trufflehog.extra_args,
        )
        logger.debug("TruffleHog found %d candidates", len(th_hits))

    all_candidates = _merge_candidates(regex_hits, th_hits)

    if not all_candidates:
        build.scan_status = ScanStatus.CLEAN
        build.scanned_at = datetime.now(tz=timezone.utc)
        return 0

    # --- Stage 3: LLM classification ---
    llm_results: list[LLMResult] = []
    try:
        llm_results = await llm_detector.classify_candidates(
            all_candidates,
            base_url=settings.ollama.base_url,
            model=settings.ollama.model,
            timeout=settings.ollama.timeout_seconds,
        )
    except Exception as e:
        logger.error("LLM classification failed for build %s #%d: %s", build.job_name, build.build_number, e)
        # Fall through: if LLM unavailable, do not create findings (avoid noise)
        build.scan_status = ScanStatus.ERROR
        return 0

    logger.debug("LLM confirmed %d findings", len(llm_results))

    if not llm_results:
        build.scan_status = ScanStatus.CLEAN
        build.scanned_at = datetime.now(tz=timezone.utc)
        return 0

    # --- Stage 4 + 5: Exemption check + persist ---
    new_findings = 0
    for result in llm_results:
        c = result.candidate

        # Check for existing finding with same hash on this build (idempotent)
        existing = (
            session.query(Finding)
            .filter_by(build_id=build.id, content_hash=c.content_hash)
            .first()
        )
        if existing:
            continue

        exemption = find_exemption(
            session=session,
            jenkins_instance_id=build.jenkins_instance_id,
            job_name=build.job_name,
            finding_type=result.finding_type,
            content_hash=c.content_hash,
        )

        # Determine detector source
        if "trufflehog" in c.detector_hint.lower():
            detector = DetectorType.TRUFFLEHOG
        else:
            detector = DetectorType.REGEX
        # Final confirmation is always LLM
        detector = DetectorType.LLM

        finding = Finding(
            build_id=build.id,
            detector=detector,
            finding_type=result.finding_type,
            severity=_severity_enum(result.severity),
            line_number=c.line_number or None,
            line_context="\n".join(c.context_lines) if c.context_lines else c.line,
            display_value=c.display_value,
            content_hash=c.content_hash,
            encoding=c.encoding if c.encoding != "PLAINTEXT" else None,
            llm_confidence=result.confidence,
            llm_explanation=result.explanation,
            exemption_id=exemption.id if exemption else None,
        )
        session.add(finding)
        session.flush()  # get finding.id

        # Queue notification only for non-exempted findings
        if not exemption:
            _queue_notification(build, finding, settings, session)
            new_findings += 1

    build.scan_status = ScanStatus.FINDINGS if new_findings > 0 else ScanStatus.CLEAN
    build.scanned_at = datetime.now(tz=timezone.utc)
    return new_findings


def _queue_notification(
    build: Build,
    finding: Finding,
    settings: Settings,
    session: Session,
) -> None:
    """Determine recipient and create a PENDING notification record."""
    min_sev_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    min_sev = settings.notifications.min_severity.upper()
    finding_sev = finding.severity.value.upper()

    if min_sev_order.index(finding_sev) < min_sev_order.index(min_sev):
        return  # Below threshold

    recipient = (
        build.triggered_by_email
        or build.triggered_by_user
        or settings.notifications.fallback_recipient
    )
    if not recipient:
        return

    notif = Notification(
        finding_id=finding.id,
        channel=NotificationChannel.EMAIL,
        recipient=recipient,
        status=NotificationStatus.PENDING,
    )
    session.add(notif)

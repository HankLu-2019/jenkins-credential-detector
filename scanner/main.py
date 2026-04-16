"""Main scanner entry point.

Usage:
  sentinel-scan run              # scan all configured instances
  sentinel-scan run --instance jenkins-main
  sentinel-scan backfill         # re-scan all historical builds
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import click
from sqlalchemy.orm import Session

from db.models import Build, JenkinsInstance, ScanState, TriggerType
from db.session import make_session_factory
from notifications.apprise_sender import send_pending_notifications
from scanner.config import load_settings
from scanner.discovery import new_builds
from scanner.pipeline import process_build_log
from scanner.provenance import parse_build_xml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sentinel")


def _get_or_create_instance(session: Session, name: str, jobs_path: str) -> JenkinsInstance:
    inst = session.query(JenkinsInstance).filter_by(name=name).first()
    if not inst:
        inst = JenkinsInstance(name=name, jobs_path=jobs_path)
        session.add(inst)
        session.flush()
    return inst


def _get_scan_state(session: Session, instance_id: int, job_name: str) -> ScanState:
    state = (
        session.query(ScanState)
        .filter_by(jenkins_instance_id=instance_id, job_name=job_name)
        .first()
    )
    if not state:
        state = ScanState(jenkins_instance_id=instance_id, job_name=job_name)
        session.add(state)
        session.flush()
    return state


def _get_or_create_build(
    session: Session, instance_id: int, job_name: str, build_number: int
) -> Build:
    build = (
        session.query(Build)
        .filter_by(
            jenkins_instance_id=instance_id,
            job_name=job_name,
            build_number=build_number,
        )
        .first()
    )
    if not build:
        build = Build(
            jenkins_instance_id=instance_id,
            job_name=job_name,
            build_number=build_number,
        )
        session.add(build)
        session.flush()
    return build


async def _scan_instance(instance_name: str | None, settings, session_factory) -> None:
    for inst_cfg in settings.jenkins_instances:
        if instance_name and inst_cfg.name != instance_name:
            continue

        logger.info("Scanning Jenkins instance: %s (%s)", inst_cfg.name, inst_cfg.jobs_path)

        with session_factory() as session:
            db_inst = _get_or_create_instance(session, inst_cfg.name, str(inst_cfg.jobs_path))
            session.commit()

        # Build last_scanned map outside the session to avoid long transactions
        with session_factory() as session:
            states = (
                session.query(ScanState)
                .filter_by(jenkins_instance_id=db_inst.id)
                .all()
            )
            last_scanned = {s.job_name: s.last_scanned_build_number for s in states}

        builds = new_builds(inst_cfg.jobs_path, last_scanned)
        logger.info("Found %d new builds to scan", len(builds))

        for build_dir in sorted(builds, key=lambda b: (b.job_name, b.build_number)):
            with session_factory() as session:
                db_build = _get_or_create_build(
                    session, db_inst.id, build_dir.job_name, build_dir.build_number
                )

                # Parse provenance from build.xml
                prov = parse_build_xml(build_dir.build_xml_path)
                db_build.trigger_type = TriggerType[prov.trigger_type]
                db_build.gerrit_change_id = prov.gerrit_change_id
                db_build.gerrit_change_number = prov.gerrit_change_number
                db_build.gerrit_project = prov.gerrit_project
                db_build.gerrit_branch = prov.gerrit_branch
                db_build.gerrit_patchset = prov.gerrit_patchset
                db_build.upstream_job = prov.upstream_job
                db_build.upstream_build_number = prov.upstream_build_number
                db_build.triggered_by_user = prov.triggered_by_user
                db_build.triggered_by_email = prov.triggered_by_email
                db_build.build_started_at = prov.build_started_at

                new_count = await process_build_log(db_build, build_dir.log_path, settings, session)

                # Update scan state
                state = _get_scan_state(session, db_inst.id, build_dir.job_name)
                if build_dir.build_number > state.last_scanned_build_number:
                    state.last_scanned_build_number = build_dir.build_number
                state.last_scan_at = datetime.now(tz=timezone.utc)

                session.commit()

                if new_count:
                    logger.info(
                        "  %s #%d → %d finding(s)",
                        build_dir.job_name, build_dir.build_number, new_count,
                    )

        # Send all pending notifications after scanning this instance
        if settings.notifications.channels or settings.notifications.fallback_recipient:
            with session_factory() as session:
                sent = send_pending_notifications(
                    session=session,
                    apprise_urls=settings.notifications.channels,
                    fallback_recipient=settings.notifications.fallback_recipient,
                )
                if sent:
                    logger.info("Sent %d notification(s) for instance %s", sent, inst_cfg.name)


@click.group()
@click.option("--config", default=None, help="Path to config.yml")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    ctx.ensure_object(dict)
    settings = load_settings(config)
    ctx.obj["settings"] = settings
    ctx.obj["session_factory"] = make_session_factory(settings.database_url)


@cli.command()
@click.option("--instance", default=None, help="Limit scan to one Jenkins instance by name")
@click.pass_context
def run(ctx: click.Context, instance: str | None) -> None:
    """Scan new builds across all configured Jenkins instances."""
    settings = ctx.obj["settings"]
    session_factory = ctx.obj["session_factory"]
    asyncio.run(_scan_instance(instance, settings, session_factory))


@cli.command()
@click.pass_context
def backfill(ctx: click.Context) -> None:
    """Reset scan state and re-scan all historical builds."""
    settings = ctx.obj["settings"]
    session_factory = ctx.obj["session_factory"]
    with session_factory() as session:
        session.query(ScanState).delete()
        session.commit()
    logger.info("Scan state cleared — running full backfill")
    asyncio.run(_scan_instance(None, settings, session_factory))

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import StatsOut
from db.models import Build, Finding, ScanStatus, Severity

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/", response_model=StatsOut)
def get_stats(session: Session = Depends(get_session)):
    sev_counts = (
        session.query(Finding.severity, func.count(Finding.id))
        .group_by(Finding.severity)
        .all()
    )
    sev_map = {s.value: c for s, c in sev_counts}

    total = sum(sev_map.values())
    open_count = (
        session.query(func.count(Finding.id))
        .filter(Finding.exemption_id.is_(None))
        .scalar()
        or 0
    )

    total_scanned = (
        session.query(func.count(Build.id))
        .filter(Build.scan_status != ScanStatus.PENDING)
        .scalar()
        or 0
    )
    with_findings = (
        session.query(func.count(Build.id))
        .filter(Build.scan_status == ScanStatus.FINDINGS)
        .scalar()
        or 0
    )

    # Top 10 jobs by finding count
    top_jobs_q = (
        session.query(Build.job_name, func.count(Finding.id).label("cnt"))
        .join(Finding, Finding.build_id == Build.id)
        .filter(Finding.exemption_id.is_(None))
        .group_by(Build.job_name)
        .order_by(func.count(Finding.id).desc())
        .limit(10)
        .all()
    )
    top_jobs = [{"job_name": j, "count": c} for j, c in top_jobs_q]

    return StatsOut(
        total_findings=total,
        open_findings=open_count,
        critical=sev_map.get("CRITICAL", 0),
        high=sev_map.get("HIGH", 0),
        medium=sev_map.get("MEDIUM", 0),
        low=sev_map.get("LOW", 0),
        total_builds_scanned=total_scanned,
        builds_with_findings=with_findings,
        top_jobs=top_jobs,
    )

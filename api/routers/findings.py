from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import FindingOut
from db.models import Finding, Severity

router = APIRouter(prefix="/findings", tags=["findings"])

_SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@router.get("/", response_model=list[FindingOut])
def list_findings(
    build_id: int | None = Query(None),
    instance_id: int | None = Query(None),
    job_name: str | None = Query(None),
    severity: str | None = Query(None),
    finding_type: str | None = Query(None),
    open_only: bool = Query(False, description="Exclude exempted findings"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    session: Session = Depends(get_session),
):
    q = session.query(Finding)

    if build_id is not None:
        q = q.filter(Finding.build_id == build_id)

    if instance_id is not None:
        from db.models import Build
        q = q.join(Build).filter(Build.jenkins_instance_id == instance_id)

    if job_name:
        from db.models import Build
        q = q.join(Build).filter(Build.job_name.ilike(f"%{job_name}%"))

    if severity:
        try:
            q = q.filter(Finding.severity == Severity[severity.upper()])
        except KeyError:
            raise HTTPException(400, f"Invalid severity: {severity}")

    if finding_type:
        q = q.filter(Finding.finding_type.ilike(f"%{finding_type}%"))

    if open_only:
        q = q.filter(Finding.exemption_id.is_(None))

    q = q.order_by(Finding.created_at.desc()).offset(offset).limit(limit)
    return q.all()


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(finding_id: int, session: Session = Depends(get_session)):
    f = session.get(Finding, finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    return f

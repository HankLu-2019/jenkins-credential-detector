from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import BuildOut
from db.models import Build, Finding

router = APIRouter(prefix="/builds", tags=["builds"])


@router.get("/", response_model=list[BuildOut])
def list_builds(
    instance_id: int | None = Query(None),
    job_name: str | None = Query(None),
    scan_status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    session: Session = Depends(get_session),
):
    q = session.query(Build)

    if instance_id is not None:
        q = q.filter(Build.jenkins_instance_id == instance_id)
    if job_name:
        q = q.filter(Build.job_name.ilike(f"%{job_name}%"))
    if scan_status:
        q = q.filter(Build.scan_status == scan_status.upper())

    builds = q.order_by(Build.scanned_at.desc()).offset(offset).limit(limit).all()

    # Attach finding counts
    build_ids = [b.id for b in builds]
    counts = (
        session.query(Finding.build_id, func.count(Finding.id))
        .filter(Finding.build_id.in_(build_ids))
        .group_by(Finding.build_id)
        .all()
    )
    count_map = dict(counts)

    result = []
    for b in builds:
        out = BuildOut.model_validate(b)
        out.finding_count = count_map.get(b.id, 0)
        result.append(out)
    return result


@router.get("/{build_id}", response_model=BuildOut)
def get_build(build_id: int, session: Session = Depends(get_session)):
    b = session.get(Build, build_id)
    if not b:
        raise HTTPException(404, "Build not found")
    out = BuildOut.model_validate(b)
    out.finding_count = (
        session.query(func.count(Finding.id)).filter_by(build_id=build_id).scalar() or 0
    )
    return out

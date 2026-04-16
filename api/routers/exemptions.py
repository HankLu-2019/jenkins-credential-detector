from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import ExemptionIn, ExemptionOut
from db.models import Exemption, Finding

router = APIRouter(prefix="/exemptions", tags=["exemptions"])


@router.get("/", response_model=list[ExemptionOut])
def list_exemptions(session: Session = Depends(get_session)):
    return session.query(Exemption).order_by(Exemption.created_at.desc()).all()


@router.post("/", response_model=ExemptionOut, status_code=201)
def create_exemption(body: ExemptionIn, session: Session = Depends(get_session)):
    exemption = Exemption(**body.model_dump())
    session.add(exemption)
    session.commit()
    session.refresh(exemption)
    return exemption


@router.delete("/{exemption_id}", status_code=204)
def delete_exemption(exemption_id: int, session: Session = Depends(get_session)):
    exemption = session.get(Exemption, exemption_id)
    if not exemption:
        raise HTTPException(404, "Exemption not found")
    # Unlink any findings pointing to this exemption
    session.query(Finding).filter_by(exemption_id=exemption_id).update(
        {"exemption_id": None}
    )
    session.delete(exemption)
    session.commit()


@router.post("/from-finding/{finding_id}", response_model=ExemptionOut, status_code=201)
def create_exemption_from_finding(
    finding_id: int,
    reason: str = "",
    created_by: str = "",
    session: Session = Depends(get_session),
):
    """Convenience endpoint: create an exemption pre-filled from a finding."""
    finding = session.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")

    build = finding.build
    exemption = Exemption(
        jenkins_instance_id=build.jenkins_instance_id,
        job_name_pattern=build.job_name,
        finding_type=finding.finding_type,
        content_hash=finding.content_hash,
        reason=reason,
        created_by=created_by,
    )
    session.add(exemption)
    finding.exemption_id = None  # will be linked on next scan; update now too
    session.flush()
    finding.exemption_id = exemption.id
    session.commit()
    session.refresh(exemption)
    return exemption

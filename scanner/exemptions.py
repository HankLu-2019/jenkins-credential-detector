"""Exemption engine — checks whether a finding should be suppressed.

Exemptions are stored in the DB and matched against findings using:
  - jenkins_instance_id (NULL = any instance)
  - job_name_pattern    (NULL = any job; supports % wildcard via SQL LIKE)
  - finding_type        (NULL = any type)
  - content_hash        (NULL = match by type/job only)
  - expires_at          (NULL = permanent; skip if past expiry)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from db.models import Exemption


def find_exemption(
    session: Session,
    jenkins_instance_id: int,
    job_name: str,
    finding_type: str,
    content_hash: str,
) -> Exemption | None:
    """Return the first matching active exemption, or None."""
    now = datetime.now(tz=timezone.utc)

    rows = (
        session.query(Exemption)
        .filter(
            # Not expired
            or_(Exemption.expires_at.is_(None), Exemption.expires_at > now),
            # Instance: NULL matches any
            or_(
                Exemption.jenkins_instance_id.is_(None),
                Exemption.jenkins_instance_id == jenkins_instance_id,
            ),
            # Finding type: NULL matches any
            or_(
                Exemption.finding_type.is_(None),
                func.upper(Exemption.finding_type) == finding_type.upper(),
            ),
            # Content hash: NULL means type/job match is enough
            or_(
                Exemption.content_hash.is_(None),
                Exemption.content_hash == content_hash,
            ),
        )
        .all()
    )

    # Apply job_name_pattern filtering (LIKE semantics with % wildcard)
    for row in rows:
        if row.job_name_pattern is None:
            return row
        # Convert SQL LIKE pattern to a simple prefix/suffix check
        pattern = row.job_name_pattern
        if "%" not in pattern:
            if job_name == pattern:
                return row
        else:
            # Simple glob: support leading/trailing % only
            if pattern.startswith("%") and pattern.endswith("%"):
                if pattern[1:-1] in job_name:
                    return row
            elif pattern.startswith("%"):
                if job_name.endswith(pattern[1:]):
                    return row
            elif pattern.endswith("%"):
                if job_name.startswith(pattern[:-1]):
                    return row

    return None

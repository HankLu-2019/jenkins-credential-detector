"""Parse build.xml to extract build provenance (cause information).

Jenkins writes cause data to disk as XML. This module parses all four
trigger types without requiring a live Jenkins API connection.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

TriggerTypeStr = Literal["GERRIT", "UPSTREAM", "TIMER", "MANUAL", "UNKNOWN"]


@dataclass
class BuildProvenance:
    trigger_type: TriggerTypeStr = "UNKNOWN"

    # GERRIT
    gerrit_change_id: str | None = None
    gerrit_change_number: int | None = None
    gerrit_project: str | None = None
    gerrit_branch: str | None = None
    gerrit_patchset: int | None = None

    # UPSTREAM
    upstream_job: str | None = None
    upstream_build_number: int | None = None

    # MANUAL / common
    triggered_by_user: str | None = None
    triggered_by_email: str | None = None

    # Build metadata
    build_started_at: datetime | None = None


def _text(element: ET.Element | None, tag: str, default: str = "") -> str:
    if element is None:
        return default
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else default


def _int_text(element: ET.Element | None, tag: str) -> int | None:
    val = _text(element, tag)
    try:
        return int(val) if val else None
    except ValueError:
        return None


def _parse_gerrit_cause(cause_el: ET.Element) -> BuildProvenance:
    prov = BuildProvenance(trigger_type="GERRIT")

    # The event element may be nested under different class names depending
    # on the Gerrit trigger plugin version.
    event = cause_el.find(".//event")
    if event is None:
        event = cause_el.find(".//change")
    change = cause_el.find(".//change")
    patchset = cause_el.find(".//patchSet")

    if change is not None:
        prov.gerrit_change_id = _text(change, "id") or None
        prov.gerrit_change_number = _int_text(change, "number")
        prov.gerrit_project = _text(change, "project") or None
        prov.gerrit_branch = _text(change, "branch") or None

        owner = change.find("owner")
        if owner is not None:
            prov.triggered_by_email = _text(owner, "email") or None
            prov.triggered_by_user = _text(owner, "name") or None

    if patchset is not None:
        prov.gerrit_patchset = _int_text(patchset, "number")

    return prov


def _parse_upstream_cause(cause_el: ET.Element) -> BuildProvenance:
    return BuildProvenance(
        trigger_type="UPSTREAM",
        upstream_job=_text(cause_el, "upstreamProject") or None,
        upstream_build_number=_int_text(cause_el, "upstreamBuild"),
    )


def _parse_user_cause(cause_el: ET.Element) -> BuildProvenance:
    return BuildProvenance(
        trigger_type="MANUAL",
        triggered_by_user=_text(cause_el, "userName") or _text(cause_el, "userId") or None,
        triggered_by_email=None,  # Jenkins UserIdCause does not expose email on disk
    )


def parse_build_xml(build_xml_path: Path) -> BuildProvenance:
    """Parse a build.xml file and return a BuildProvenance instance."""
    try:
        tree = ET.parse(build_xml_path)
    except (ET.ParseError, OSError):
        return BuildProvenance()

    root = tree.getroot()

    # Extract build start time
    prov = BuildProvenance()
    start_time_el = root.find("startTime")
    if start_time_el is not None and start_time_el.text:
        try:
            ms = int(start_time_el.text.strip())
            prov.build_started_at = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

    # Find CauseAction → causeBag → first cause element
    for action in root.findall(".//actions/*"):
        # Handle both <hudson.model.CauseAction> and nested structures
        cause_bag = action.find("causeBag")
        causes = list(cause_bag) if cause_bag is not None else list(action)

        for cause in causes:
            tag = cause.tag.lower()

            if "gerritcause" in tag:
                found = _parse_gerrit_cause(cause)
                found.build_started_at = prov.build_started_at
                return found

            if "upstreamcause" in tag:
                found = _parse_upstream_cause(cause)
                found.build_started_at = prov.build_started_at
                return found

            if "timertriggercause" in tag:
                prov.trigger_type = "TIMER"
                return prov

            if "useridcause" in tag or "usercause" in tag:
                found = _parse_user_cause(cause)
                found.build_started_at = prov.build_started_at
                return found

    return prov

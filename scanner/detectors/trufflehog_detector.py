"""TruffleHog v3 subprocess wrapper.

Runs: trufflehog filesystem --json --no-update <log_path>
Parses JSON output and merges results with regex candidates.
Skips gracefully if trufflehog binary is not installed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .regex_detector import Candidate, _mask


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().encode()).hexdigest()


def _severity_from_trufflehog(raw: dict) -> str:
    """Map TruffleHog's detector metadata to our severity levels."""
    # TruffleHog doesn't have a native severity field; infer from detector name.
    name = (raw.get("DetectorName") or "").upper()
    if any(k in name for k in ("AWS", "GITHUB", "PRIVATE", "RSA", "SSH", "GCP", "AZURE")):
        return "CRITICAL"
    if any(k in name for k in ("SLACK", "STRIPE", "TWILIO", "SENDGRID", "GITLAB")):
        return "HIGH"
    return "MEDIUM"


def _map_finding_type(raw: dict) -> str:
    """Derive a normalized finding type string from TruffleHog output."""
    name = raw.get("DetectorName") or raw.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {}).get("file", "UNKNOWN")
    return name.upper().replace(" ", "_").replace("-", "_")


def scan_log(log_path: Path, binary: str = "trufflehog", extra_args: list[str] | None = None) -> list[Candidate]:
    """Run TruffleHog on a single log file and return Candidate objects."""
    cmd = [
        binary, "filesystem",
        "--json",
        "--no-update",
        str(log_path),
    ] + (extra_args or [])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        # trufflehog not installed — skip silently
        return []
    except subprocess.TimeoutExpired:
        return []

    candidates: list[Candidate] = []
    seen: set[str] = set()

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            finding = json.loads(line)
        except json.JSONDecodeError:
            continue

        # TruffleHog v3 JSON structure:
        # { "SourceMetadata": {...}, "DetectorName": "...",
        #   "Raw": "...", "RawV2": "...", "Verified": true/false, ... }
        raw_value = finding.get("RawV2") or finding.get("Raw") or ""
        if not raw_value:
            continue

        h = _sha256(raw_value)
        if h in seen:
            continue
        seen.add(h)

        # Try to get line number from source metadata
        line_number: int | None = None
        fs_meta = (
            finding.get("SourceMetadata", {})
            .get("Data", {})
            .get("Filesystem", {})
        )
        if isinstance(fs_meta, dict):
            line_number = fs_meta.get("line")

        candidates.append(
            Candidate(
                line_number=line_number or 0,
                line="<from TruffleHog>",
                context_lines=[],
                raw_value=raw_value,
                display_value=_mask(raw_value),
                content_hash=h,
                finding_type=_map_finding_type(finding),
                severity=_severity_from_trufflehog(finding),
                encoding="PLAINTEXT",
                detector_hint=f"TruffleHog:{finding.get('DetectorName', 'unknown')}",
            )
        )

    return candidates

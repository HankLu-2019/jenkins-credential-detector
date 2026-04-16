"""Regex-based credential pre-filter.

Two passes:
  Pass A — plaintext credential patterns (assignments, known token formats).
  Pass B — base64 candidates (Authorization: Basic, docker auth, JWT,
            bare base64 near credential keywords).

Returns a list of Candidate objects with enough context for the LLM stage.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

EncodingType = Literal["PLAINTEXT", "BASE64", "BASE64URL", "JWT"]

# ---------------------------------------------------------------------------
# Patterns — Pass A: plaintext
# ---------------------------------------------------------------------------

_PLAINTEXT_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    # (name, pattern, finding_type, severity)
    # NOTE: vendor-specific patterns MUST appear before generic catch-alls so
    # that deduplication (by content_hash) keeps the more precise finding_type.

    # AWS
    ("AWS Access Key", re.compile(r"(?<![A-Z0-9])(AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"), "AWS_ACCESS_KEY", "CRITICAL"),
    ("AWS Secret Key", re.compile(r"(?i)aws[_\-\s]*secret[_\-\s]*(?:access[_\-\s]*)?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+]{40})"), "AWS_SECRET_KEY", "CRITICAL"),

    # GitHub / GitLab — before generic token pattern
    ("GitHub token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9]{20,}"), "GITHUB_TOKEN", "CRITICAL"),
    ("GitLab token", re.compile(r"glpat-[A-Za-z0-9\-_]{20,}"), "GITLAB_TOKEN", "CRITICAL"),

    # JWT — before generic token pattern (three base64url segments)
    ("JWT token", re.compile(
        r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'
    ), "JWT_TOKEN", "HIGH"),

    # Slack
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "SLACK_TOKEN", "HIGH"),

    # Generic assignment patterns
    ("Password assignment", re.compile(
        r'(?i)(?:password|passwd|pwd|pass)\s*[:=]\s*["\']?([^\s"\'\\]{8,})["\']?'
    ), "GENERIC_PASSWORD", "HIGH"),
    ("Secret assignment", re.compile(
        r'(?i)(?:secret|api[_\-]?secret|client[_\-]?secret)\s*[:=]\s*["\']?([^\s"\'\\]{8,})["\']?'
    ), "GENERIC_SECRET", "HIGH"),
    ("Token assignment", re.compile(
        r'(?i)(?:token|api[_\-]?token|auth[_\-]?token|access[_\-]?token)\s*[:=]\s*["\']?([A-Za-z0-9_\-\.]{16,})["\']?'
    ), "GENERIC_TOKEN", "HIGH"),

    # Private keys
    ("PEM private key", re.compile(r"-----BEGIN\s+(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "PRIVATE_KEY", "CRITICAL"),
    ("PEM certificate", re.compile(r"-----BEGIN CERTIFICATE-----"), "CERTIFICATE", "MEDIUM"),

    # Database connection strings
    ("DB connection string", re.compile(
        r'(?i)(?:mysql|postgresql|postgres|mongodb|redis|jdbc)\s*://[^:@\s]+:[^@\s]{4,}@'
    ), "DB_CONNECTION_STRING", "CRITICAL"),

    # Generic high-entropy bearer tokens
    ("Bearer token", re.compile(
        r'(?i)Authorization:\s*Bearer\s+([A-Za-z0-9_\-\.]{20,})'
    ), "BEARER_TOKEN", "HIGH"),

    # SSH private key embedded
    ("SSH private key", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"), "SSH_PRIVATE_KEY", "CRITICAL"),

    # Google API key
    ("Google API key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "GOOGLE_API_KEY", "HIGH"),
]

# ---------------------------------------------------------------------------
# Patterns — Pass B: base64 candidates
# ---------------------------------------------------------------------------

# High-confidence: known credential-bearing contexts
_B64_HIGH_CONFIDENCE: list[tuple[str, re.Pattern, str]] = [
    # Authorization: Basic <base64>
    ("HTTP Basic Auth", re.compile(
        r'(?i)Authorization:\s*Basic\s+([A-Za-z0-9+/]{8,}={0,2})'
    ), "HTTP_BASIC_AUTH"),

    # Docker config.json "auth" field
    ("Docker auth", re.compile(
        r'"auth"\s*:\s*"([A-Za-z0-9+/]{8,}={0,2})"'
    ), "DOCKER_AUTH"),

    # Git URL with embedded credentials
    ("Git URL credentials", re.compile(
        r'https?://([A-Za-z0-9+/]{4,}={0,2}):([A-Za-z0-9+/]{4,}={0,2})@'
    ), "GIT_URL_CREDENTIALS"),
]

# JWT: three base64url parts separated by dots
_JWT_PATTERN = re.compile(
    r'eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'
)

# Bare base64 near credential keywords (medium confidence)
_B64_KEYWORD_RE = re.compile(
    r'(?i)(?:password|passwd|secret|token|key|credential|auth)\s*[:=]\s*'
    r'([A-Za-z0-9+/]{20,}={0,2})'
)

# Valid base64 charset check
_B64_VALID_RE = re.compile(r'^[A-Za-z0-9+/]+=*$')
_B64URL_VALID_RE = re.compile(r'^[A-Za-z0-9_\-]+=*$')

# ---------------------------------------------------------------------------
# Candidate dataclass
# ---------------------------------------------------------------------------

CONTEXT_WINDOW = 5  # lines before and after


@dataclass
class Candidate:
    line_number: int        # 1-based
    line: str               # the actual matching line
    context_lines: list[str] = field(default_factory=list)  # ±CONTEXT_WINDOW lines
    raw_value: str = ""     # extracted value (decoded if base64)
    display_value: str = "" # masked: first 6, last 3 chars
    content_hash: str = ""  # SHA256 of normalized raw_value
    finding_type: str = ""
    severity: str = "MEDIUM"
    encoding: EncodingType = "PLAINTEXT"
    detector_hint: str = ""  # human label for this pattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask(value: str) -> str:
    """Return a display-safe masked version: first 6, last 3 chars."""
    if len(value) <= 9:
        return "*" * len(value)
    return value[:6] + "***...***" + value[-3:]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().encode()).hexdigest()


def _decode_b64(encoded: str) -> str | None:
    """Try to decode base64; return decoded string or None on failure."""
    # Pad if needed
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(padded)
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return None


def _is_credential_shaped(decoded: str) -> bool:
    """Heuristic: does the decoded value look like a credential?"""
    if ":" in decoded:
        return True
    if decoded.startswith("-----BEGIN"):
        return True
    if len(decoded) in (16, 24, 32, 48, 64):  # common key lengths
        return True
    return False


def _build_candidate(
    line_number: int,
    line: str,
    lines: list[str],
    raw_value: str,
    finding_type: str,
    severity: str,
    encoding: EncodingType,
    hint: str,
) -> Candidate:
    start = max(0, line_number - 1 - CONTEXT_WINDOW)
    end = min(len(lines), line_number + CONTEXT_WINDOW)
    context = lines[start:end]

    display = _mask(raw_value)
    # Redact the raw value in context for safe storage
    safe_context = [l.replace(raw_value, "<REDACTED>") for l in context]

    return Candidate(
        line_number=line_number,
        line=line.replace(raw_value, "<REDACTED>"),
        context_lines=safe_context,
        raw_value=raw_value,
        display_value=display,
        content_hash=_sha256(raw_value),
        finding_type=finding_type,
        severity=severity,
        encoding=encoding,
        detector_hint=hint,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_log(log_path: Path) -> list[Candidate]:
    """Run both regex passes on a log file and return candidates."""
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    candidates: list[Candidate] = []
    seen_hashes: set[str] = set()

    def _add(c: Candidate) -> None:
        if c.content_hash not in seen_hashes:
            seen_hashes.add(c.content_hash)
            candidates.append(c)

    # --- Pass A: plaintext patterns ---
    for line_no, line in enumerate(lines, start=1):
        for hint, pattern, ftype, severity in _PLAINTEXT_PATTERNS:
            for m in pattern.finditer(line):
                # Use group(1) if available (captured group = the value),
                # else the full match.
                value = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                if len(value) < 4:
                    continue
                _add(_build_candidate(line_no, line, lines, value, ftype, severity, "PLAINTEXT", hint))

    # --- Pass B: base64 ---

    for line_no, line in enumerate(lines, start=1):
        # High-confidence base64 contexts
        for hint, pattern, ftype in _B64_HIGH_CONFIDENCE:
            for m in pattern.finditer(line):
                encoded = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                decoded = _decode_b64(encoded)
                if decoded:
                    _add(_build_candidate(
                        line_no, line, lines, decoded, ftype, "CRITICAL", "BASE64", hint
                    ))

        # Medium-confidence: bare base64 near keywords
        for m in _B64_KEYWORD_RE.finditer(line):
            encoded = m.group(1)
            if not _B64_VALID_RE.match(encoded):
                continue
            decoded = _decode_b64(encoded)
            if decoded and _is_credential_shaped(decoded):
                _add(_build_candidate(
                    line_no, line, lines, decoded, "GENERIC_BASE64_CREDENTIAL",
                    "MEDIUM", "BASE64", "base64 near keyword"
                ))

    return candidates

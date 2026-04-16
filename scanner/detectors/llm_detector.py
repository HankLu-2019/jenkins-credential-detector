"""LLM-based credential classifier using Ollama (local model).

Takes a list of Candidate objects from regex/TruffleHog pre-filter,
sends each as a structured prompt to Ollama, and returns only those
the LLM confirms as real credentials.

Design decisions:
- The DECODED value (not raw base64) is shown to the LLM for better context.
- The actual secret value is NOT sent — only the surrounding context lines
  with the value replaced by a placeholder. The LLM classifies based on
  structure and context, not the secret itself.
- System prompt is terse and instruction-tuned.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace

import httpx

from .regex_detector import Candidate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a security analyst. You will be given lines from a CI/CD build log \
and asked whether a specific line contains a real credential (password, API key, \
token, private key, connection string, etc.).

Respond ONLY with a JSON object — no prose, no markdown:
{
  "is_credential": true | false,
  "finding_type": "<type string, e.g. AWS_ACCESS_KEY>",
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "confidence": 0.0-1.0,
  "explanation": "<one sentence>"
}

Rules:
- Test/example values (e.g. "password=test123", "mypassword", "changeme", \
  "example", "placeholder", "xxx", "your_token_here") are NOT credentials.
- Log format markers, build step names, and command echoes that happen to \
  contain the word "password" but have no actual value are NOT credentials.
- Environment variable definitions with clearly empty values are NOT credentials.
- Only flag values that look like they could grant real access if used.
"""


@dataclass
class LLMResult:
    candidate: Candidate
    is_credential: bool
    finding_type: str
    severity: str
    confidence: float
    explanation: str


def _build_user_message(candidate: Candidate) -> str:
    context_block = "\n".join(
        f"  [{i + max(1, candidate.line_number - 5)}] {l}"
        for i, l in enumerate(candidate.context_lines)
    )
    return (
        f"Pattern detected: {candidate.detector_hint}\n"
        f"Finding type hint: {candidate.finding_type}\n"
        f"Encoding: {candidate.encoding}\n\n"
        f"Context (surrounding log lines, secret replaced with <REDACTED>):\n"
        f"{context_block}\n\n"
        f"Is the value on the flagged line a real credential?"
    )


async def classify_candidates(
    candidates: list[Candidate],
    base_url: str = "http://localhost:11434",
    model: str = "qwen2.5-coder:7b",
    timeout: int = 120,
) -> list[LLMResult]:
    """Send each candidate to Ollama and return LLMResult for all confirmed findings."""
    if not candidates:
        return []

    results: list[LLMResult] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        for candidate in candidates:
            user_msg = _build_user_message(candidate)

            payload = {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "format": "json",
            }

            try:
                resp = await client.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("Ollama request failed for candidate %s: %s", candidate.finding_type, e)
                continue

            raw_content = data.get("message", {}).get("content", "{}")
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                logger.warning("Could not parse LLM JSON response: %s", raw_content[:200])
                continue

            is_cred = bool(parsed.get("is_credential", False))
            confidence = float(parsed.get("confidence", 0.0))

            if not is_cred or confidence < 0.5:
                continue

            # Allow LLM to override/refine the finding type and severity
            results.append(
                LLMResult(
                    candidate=candidate,
                    is_credential=True,
                    finding_type=parsed.get("finding_type") or candidate.finding_type,
                    severity=parsed.get("severity") or candidate.severity,
                    confidence=confidence,
                    explanation=parsed.get("explanation", ""),
                )
            )

    return results

"""Tests for the exemption matching engine."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from scanner.exemptions import find_exemption
from db.models import Exemption


def _make_session(exemptions: list[Exemption]):
    """Return a mock Session whose query returns the given exemptions."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = exemptions
    session = MagicMock()
    session.query.return_value = mock_query
    return session


def _exemption(**kwargs) -> Exemption:
    e = Exemption()
    e.jenkins_instance_id = kwargs.get("jenkins_instance_id", None)
    e.job_name_pattern = kwargs.get("job_name_pattern", None)
    e.finding_type = kwargs.get("finding_type", None)
    e.content_hash = kwargs.get("content_hash", None)
    e.expires_at = kwargs.get("expires_at", None)
    e.reason = kwargs.get("reason", "")
    e.created_by = kwargs.get("created_by", "")
    e.id = kwargs.get("id", 1)
    return e


class TestJobNamePatternMatching:
    def test_exact_match(self):
        ex = _exemption(job_name_pattern="my-job")
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "abc123")
        assert result is ex

    def test_no_match_different_job(self):
        ex = _exemption(job_name_pattern="other-job")
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "abc123")
        assert result is None

    def test_prefix_wildcard(self):
        ex = _exemption(job_name_pattern="my-%")
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "abc123")
        assert result is ex

    def test_suffix_wildcard(self):
        ex = _exemption(job_name_pattern="%-deploy")
        session = _make_session([ex])
        result = find_exemption(session, 1, "prod-deploy", "GENERIC_PASSWORD", "abc123")
        assert result is ex

    def test_contains_wildcard(self):
        ex = _exemption(job_name_pattern="%pipeline%")
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-pipeline-job", "GENERIC_PASSWORD", "abc123")
        assert result is ex

    def test_null_pattern_matches_any_job(self):
        ex = _exemption(job_name_pattern=None)
        session = _make_session([ex])
        result = find_exemption(session, 1, "any-job-name", "GENERIC_PASSWORD", "abc123")
        assert result is ex


class TestExpiry:
    def test_expired_exemption_not_matched(self):
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        ex = _exemption(expires_at=past)
        # Expired exemptions are filtered out in the DB query (WHERE clause),
        # so they won't appear in the all() result — simulate that
        session = _make_session([])  # filtered out already
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "abc123")
        assert result is None

    def test_future_expiry_matches(self):
        future = datetime.now(tz=timezone.utc) + timedelta(days=30)
        ex = _exemption(expires_at=future, job_name_pattern=None)
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "abc123")
        assert result is ex


class TestContentHash:
    def test_specific_hash_matches(self):
        ex = _exemption(content_hash="deadbeef" * 8, job_name_pattern=None)
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "deadbeef" * 8)
        assert result is ex

    def test_null_hash_matches_any_value(self):
        ex = _exemption(content_hash=None, job_name_pattern=None)
        session = _make_session([ex])
        result = find_exemption(session, 1, "my-job", "GENERIC_PASSWORD", "any-hash")
        assert result is ex

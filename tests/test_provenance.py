"""Tests for build.xml provenance parsing."""

from pathlib import Path

import pytest

from scanner.provenance import parse_build_xml

FIXTURES = Path(__file__).parent / "fixtures"


def test_gerrit_cause():
    prov = parse_build_xml(FIXTURES / "build_gerrit.xml")
    assert prov.trigger_type == "GERRIT"
    assert prov.gerrit_project == "my-repo"
    assert prov.gerrit_branch == "main"
    assert prov.gerrit_change_id == "Iabcdef1234567890abcdef1234567890abcdef12"
    assert prov.gerrit_change_number == 42
    assert prov.gerrit_patchset == 3
    assert prov.triggered_by_email == "alice@example.com"
    assert prov.triggered_by_user == "Alice Dev"
    assert prov.build_started_at is not None


def test_upstream_cause():
    prov = parse_build_xml(FIXTURES / "build_upstream.xml")
    assert prov.trigger_type == "UPSTREAM"
    assert prov.upstream_job == "parent-pipeline"
    assert prov.upstream_build_number == 17


def test_timer_cause():
    prov = parse_build_xml(FIXTURES / "build_timer.xml")
    assert prov.trigger_type == "TIMER"


def test_manual_cause():
    prov = parse_build_xml(FIXTURES / "build_manual.xml")
    assert prov.trigger_type == "MANUAL"
    assert prov.triggered_by_user == "John Smith"


def test_missing_file_returns_unknown():
    prov = parse_build_xml(Path("/nonexistent/build.xml"))
    assert prov.trigger_type == "UNKNOWN"

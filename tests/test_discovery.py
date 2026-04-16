"""Tests for the build discovery logic."""

from pathlib import Path

import pytest

from scanner.discovery import discover_builds, new_builds


def _make_build(base: Path, job_name: str, build_number: int, complete: bool = True) -> Path:
    """Create a fake build directory with log and build.xml."""
    build_dir = base / job_name / "builds" / str(build_number)
    build_dir.mkdir(parents=True)
    (build_dir / "log").write_text("build output\n")
    result_tag = "<result>SUCCESS</result>" if complete else ""
    (build_dir / "build.xml").write_text(
        f"<build><startTime>1000</startTime>{result_tag}</build>"
    )
    return build_dir


class TestFlatJobDiscovery:
    def test_discovers_completed_build(self, tmp_path):
        _make_build(tmp_path, "my-job", 1)
        builds = discover_builds(tmp_path)
        assert len(builds) == 1
        assert builds[0].job_name == "my-job"
        assert builds[0].build_number == 1

    def test_skips_running_build(self, tmp_path):
        _make_build(tmp_path, "my-job", 1, complete=False)
        builds = discover_builds(tmp_path)
        assert len(builds) == 0

    def test_discovers_multiple_builds(self, tmp_path):
        for n in range(1, 4):
            _make_build(tmp_path, "my-job", n)
        builds = discover_builds(tmp_path)
        assert len(builds) == 3

    def test_skips_symlinks(self, tmp_path):
        _make_build(tmp_path, "my-job", 1)
        builds_dir = tmp_path / "my-job" / "builds"
        symlink = builds_dir / "lastStableBuild"
        symlink.symlink_to(builds_dir / "1")
        builds = discover_builds(tmp_path)
        assert len(builds) == 1  # symlink not counted


class TestNestedJobDiscovery:
    def test_folder_plugin_layout(self, tmp_path):
        # Simulates: jobs_path/my-folder/jobs/child-job/builds/1/
        build_dir = tmp_path / "my-folder" / "jobs" / "child-job" / "builds" / "1"
        build_dir.mkdir(parents=True)
        (build_dir / "log").write_text("output")
        (build_dir / "build.xml").write_text("<build><result>SUCCESS</result></build>")
        builds = discover_builds(tmp_path)
        assert len(builds) == 1
        assert "child-job" in builds[0].job_name

    def test_builds_without_log_skipped(self, tmp_path):
        build_dir = tmp_path / "my-job" / "builds" / "1"
        build_dir.mkdir(parents=True)
        (build_dir / "build.xml").write_text("<build><result>SUCCESS</result></build>")
        # No log file
        builds = discover_builds(tmp_path)
        assert len(builds) == 0


class TestIncrementalScanning:
    def test_new_builds_filters_by_last_scanned(self, tmp_path):
        for n in range(1, 6):
            _make_build(tmp_path, "my-job", n)
        last_scanned = {"my-job": 3}
        builds = new_builds(tmp_path, last_scanned)
        numbers = {b.build_number for b in builds}
        assert numbers == {4, 5}

    def test_no_last_scanned_returns_all(self, tmp_path):
        for n in range(1, 4):
            _make_build(tmp_path, "my-job", n)
        builds = new_builds(tmp_path, {})
        assert len(builds) == 3

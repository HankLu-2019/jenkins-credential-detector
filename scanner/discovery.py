"""Discover Jenkins build directories under a jobs_path.

Handles three layouts:
  - Flat job:        {jobs_path}/{job}/builds/{n}/
  - Folder plugin:   {jobs_path}/{folder}/jobs/{job}/builds/{n}/
  - Multibranch:     {jobs_path}/{pipeline}/branches/{branch}/builds/{n}/

Symlinks (lastStableBuild, etc.) are skipped.
Builds still in progress (no <result> in build.xml) are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BUILD_NUM_RE = re.compile(r"^\d+$")


@dataclass
class BuildDir:
    job_name: str      # e.g. "folder/job" or "pipeline/branch-name"
    build_number: int
    build_path: Path   # absolute path to the build directory
    log_path: Path     # {build_path}/log
    build_xml_path: Path  # {build_path}/build.xml


def _is_numeric_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and _BUILD_NUM_RE.match(path.name) is not None


def _build_xml_is_complete(build_xml: Path) -> bool:
    """Return True only if the build has finished (has a <result> element)."""
    try:
        text = build_xml.read_text(errors="replace")
        return "<result>" in text
    except OSError:
        return False


def _iter_builds_under(builds_dir: Path, job_name: str) -> list[BuildDir]:
    """Yield BuildDir objects for each completed numeric build directory."""
    result = []
    if not builds_dir.is_dir():
        return result
    for entry in builds_dir.iterdir():
        if not _is_numeric_dir(entry):
            continue
        log = entry / "log"
        xml = entry / "build.xml"
        if not log.exists() or not xml.exists():
            continue
        if not _build_xml_is_complete(xml):
            continue  # build still running
        result.append(
            BuildDir(
                job_name=job_name,
                build_number=int(entry.name),
                build_path=entry,
                log_path=log,
                build_xml_path=xml,
            )
        )
    return result


def _discover_in_dir(directory: Path, prefix: str = "") -> list[BuildDir]:
    """Recursively discover all builds under a directory.

    Handles flat jobs, folder-plugin nesting (jobs/ subdirectory),
    and multibranch pipelines (branches/ subdirectory).
    """
    results: list[BuildDir] = []

    if not directory.is_dir():
        return results

    for entry in directory.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue

        if entry.name == "builds":
            # We're already inside a job directory — scan builds here.
            job_name = prefix.rstrip("/")
            results.extend(_iter_builds_under(entry, job_name))

        elif entry.name == "jobs":
            # Folder plugin: recurse into each sub-job
            for sub in entry.iterdir():
                if sub.is_dir() and not sub.is_symlink():
                    sub_prefix = f"{prefix}jobs/{sub.name}"
                    results.extend(_discover_in_dir(sub, prefix=sub_prefix + "/"))

        elif entry.name == "branches":
            # Multibranch pipeline: each branch is a sub-job
            pipeline_name = prefix.rstrip("/") or directory.name
            for branch in entry.iterdir():
                if branch.is_dir() and not branch.is_symlink():
                    job_name = f"{pipeline_name}/{branch.name}"
                    results.extend(_iter_builds_under(branch / "builds", job_name))

        else:
            # Could be a top-level job dir; recurse to find builds/
            new_prefix = f"{prefix}{entry.name}/"
            results.extend(_discover_in_dir(entry, prefix=new_prefix))

    return results


def discover_builds(jobs_path: Path) -> list[BuildDir]:
    """Return all completed builds under jobs_path, across all layouts."""
    return _discover_in_dir(jobs_path, prefix="")


def new_builds(
    jobs_path: Path,
    last_scanned: dict[str, int],  # job_name → last scanned build number
) -> list[BuildDir]:
    """Return only builds with build_number > last_scanned[job_name]."""
    all_builds = discover_builds(jobs_path)
    return [
        b
        for b in all_builds
        if b.build_number > last_scanned.get(b.job_name, 0)
    ]

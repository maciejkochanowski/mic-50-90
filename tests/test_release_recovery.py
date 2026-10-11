"""Only artifacts bound to the same successful software build may be reused."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def recovery(monkeypatch):
    tools = Path(__file__).resolve().parents[1] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    import recover_software_release
    return recover_software_release


def origin_fixture(recovery):
    sha = "a" * 40
    run = {"id": 123, "repository": {"id": 7, "full_name": "owner/repo"},
           "head_repository": {"full_name": "owner/repo"}, "head_branch": "main",
           "event": "workflow_dispatch", "path": ".github/workflows/release.yml",
           "status": "completed", "conclusion": "failure", "head_sha": sha}
    jobs = [{"id": number, "name": name, "head_sha": sha, "status": "completed", "conclusion": "success"}
            for number, name in enumerate(sorted(recovery.BUILD_JOBS), 1)]
    artifacts = [{"id": number, "name": name, "expired": False, "size_in_bytes": 5,
                  "digest": "sha256:" + "b" * 64,
                  "workflow_run": {"id": 123, "head_sha": sha, "head_branch": "main",
                                   "repository_id": 7, "head_repository_id": 7}}
                 for number, name in enumerate(sorted(recovery.ARTIFACTS), 1)]
    return run, jobs, artifacts


def test_upload_failure_can_reuse_successful_build(recovery):
    run, jobs, artifacts = origin_fixture(recovery)
    result = recovery.validate_origin(run, jobs, artifacts, "owner/repo", 123)
    assert result["source_commit"] == "a" * 40
    assert len(result["jobs"]) == 8
    assert len(result["artifacts"]) == 9


@pytest.mark.parametrize("change", ["foreign_repository", "pull_request", "other_workflow", "unfinished", "failed_job", "missing_job", "foreign_job_commit", "expired_artifact", "foreign_artifact_commit", "missing_artifact"])
def test_unverified_origin_is_rejected(recovery, change):
    run, jobs, artifacts = origin_fixture(recovery)
    if change == "foreign_repository":
        run["head_repository"]["full_name"] = "other/repo"
    elif change == "pull_request":
        run["event"] = "pull_request"
    elif change == "other_workflow":
        run["path"] = ".github/workflows/other.yml"
    elif change == "unfinished":
        run["status"] = "in_progress"
    elif change == "failed_job":
        jobs[0]["conclusion"] = "failure"
    elif change == "missing_job":
        jobs.pop()
    elif change == "foreign_job_commit":
        jobs[0]["head_sha"] = "c" * 40
    elif change == "expired_artifact":
        artifacts[0]["expired"] = True
    elif change == "foreign_artifact_commit":
        artifacts[0]["workflow_run"]["head_sha"] = "c" * 40
    elif change == "missing_artifact":
        artifacts.pop()
    with pytest.raises(ValueError):
        recovery.validate_origin(run, jobs, artifacts, "owner/repo", 123)

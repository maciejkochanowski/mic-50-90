"""Recover an Actions upload from that run's already tested, unchanged software assets."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil

from check_release_tests import EXPECTED, verify_matrix
from publish_software_release import api
from software_release import VERSION, inspect_archive

BUILD_JOBS = {"packages", "windows"} | {
    f"test ({platform}, {version})" for platform in ("ubuntu-latest", "windows-latest")
    for version in ("3.11", "3.12", "3.13")}
ARTIFACTS = EXPECTED | {"software-packages", "software-windows", "release-verification"}


def validate_origin(run, jobs, artifacts, repository, run_id):
    if (run["id"] != run_id or run["repository"]["full_name"] != repository
            or run["head_repository"]["full_name"] != repository
            or run["head_branch"] != "main" or run["event"] != "workflow_dispatch"
            or run["path"] != ".github/workflows/release.yml" or run["status"] != "completed"
            or run["conclusion"] not in {"success", "failure"}
            or not re.fullmatch(r"[0-9a-f]{40}", run["head_sha"])):
        raise ValueError("Build origin must be a completed manual software release run on main in this repository")
    selected_jobs = [job for job in jobs if job["name"] in BUILD_JOBS]
    if len(selected_jobs) != len(BUILD_JOBS) or {job["name"] for job in selected_jobs} != BUILD_JOBS:
        raise ValueError("The complete eight-job build and test matrix is required")
    if any(job["status"] != "completed" or job["conclusion"] != "success"
           or job["head_sha"] != run["head_sha"] for job in selected_jobs):
        raise ValueError("All build and test jobs must have succeeded")
    selected_artifacts = [item for item in artifacts if item["name"] in ARTIFACTS]
    if len(selected_artifacts) != len(ARTIFACTS) or {item["name"] for item in selected_artifacts} != ARTIFACTS:
        raise ValueError("The complete, unique set of original software and verification artifacts is required")
    for item in selected_artifacts:
        origin = item["workflow_run"]
        if (item["expired"] or not isinstance(item["id"], int) or item["id"] <= 0
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", item["digest"])
                or origin["id"] != run_id or origin["head_sha"] != run["head_sha"]
                or origin["head_branch"] != "main" or origin["repository_id"] != run["repository"]["id"]
                or origin["head_repository_id"] != run["repository"]["id"]):
            raise ValueError("Artifact does not belong to the verified build: " + item["name"])
    return {"status": "passed", "repository": repository, "build_run_id": run_id,
            "build_actions_run": f"https://github.com/{repository}/actions/runs/{run_id}",
            "source_commit": run["head_sha"], "build_workflow": run["path"],
            "jobs": [{key: job[key] for key in ("id", "name", "status", "conclusion")} for job in sorted(selected_jobs, key=lambda x: x["name"])],
            "artifacts": [{key: item[key] for key in ("id", "name", "size_in_bytes", "digest")} for item in sorted(selected_artifacts, key=lambda x: x["name"])]}


def fetch_build_origin(repository, run_id):
    run = api(repository, f"actions/runs/{run_id}")
    jobs = api(repository, f"actions/runs/{run_id}/jobs?per_page=100")
    artifacts = api(repository, f"actions/runs/{run_id}/artifacts?per_page=100")
    if jobs["total_count"] != len(jobs["jobs"]) or artifacts["total_count"] != len(artifacts["artifacts"]):
        raise ValueError("Unexpectedly large build; bounded origin inspection was not complete")
    return validate_origin(run, jobs["jobs"], artifacts["artifacts"], repository, run_id)


def prepare(directory, prior, verification, origin_path):
    origin = json.loads(origin_path.read_text(encoding="utf-8"))
    old_path = prior / "SOFTWARE_MANIFEST.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if (old["version"] != VERSION or old["source_commit"] != origin["source_commit"]
            or old["actions_run"] != origin["build_actions_run"]):
        raise ValueError("The original asset manifest is not bound to the verified build")
    matrix = verify_matrix(verification)
    old_files = {row["file"]: row for row in old["files"]}
    expected = set(old_files) - {"Software-test-results.zip"}
    files = {path.name: path for path in directory.iterdir() if path.is_file()}
    if set(files) != expected:
        raise ValueError("Downloaded assets differ from the original build manifest")
    rows = []
    for name, path in sorted(files.items()):
        row = inspect_archive(path)
        if row != old_files[name]:
            raise ValueError("Previously built asset changed: " + name)
        rows.append(row)
    checksum_rows = {}
    for line in (prior / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksum_rows:
            raise ValueError("Duplicate entry in original checksums")
        checksum_rows[name] = digest
    if checksum_rows.get("SOFTWARE_MANIFEST.json") != sha256(old_path.read_bytes()).hexdigest():
        raise ValueError("Original manifest checksum mismatch")
    for row in rows:
        if checksum_rows.get(row["file"]) != row["sha256"]:
            raise ValueError("Original asset checksum mismatch: " + row["file"])
    shutil.copyfile(origin_path, directory / "BUILD_ORIGIN.json")
    shutil.copyfile(old_path, directory / "BUILD_ASSET_MANIFEST.json")
    (directory / "TEST_MATRIX_VERIFICATION.json").write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    receipt = {"status": "passed", "source_commit": origin["source_commit"],
               "build_actions_run": origin["build_actions_run"], "unchanged_original_assets": rows,
               "new_material": "verification metadata and a ZIP of the original JUnit reports only"}
    (directory / "REUSED_ASSET_VERIFICATION.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    origin = commands.add_parser("origin")
    origin.add_argument("--run-id", type=int, required=True)
    origin.add_argument("--output", type=Path, required=True)
    origin.add_argument("--github-output", type=Path)
    prep = commands.add_parser("prepare")
    prep.add_argument("--directory", type=Path, required=True)
    prep.add_argument("--prior", type=Path, required=True)
    prep.add_argument("--verification", type=Path, required=True)
    prep.add_argument("--origin", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "origin":
        result = fetch_build_origin(os.environ["GITHUB_REPOSITORY"], args.run_id)
        if args.output.exists():
            parser.error("Use a new origin receipt path")
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"source_commit={result['source_commit']}\nbuild_actions_run={result['build_actions_run']}\n")
    else:
        result = prepare(args.directory, args.prior, args.verification, args.origin)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

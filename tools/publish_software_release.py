"""Publish verified software assets only from a manually dispatched Actions run."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import time
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from software_release import VERSION, inspect_archive


def api(repository, path, *, missing_ok=False, method="GET", payload=None):
    request = Request(f"https://api.github.com/repos/{repository}/{path}", method=method,
        data=None if payload is None else json.dumps(payload).encode("utf-8"), headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        if missing_ok and method == "GET" and error.code == 404:
            return None
        raise


def validate_tag(tag):
    if len(tag) > 80 or not re.fullmatch(re.escape("v" + VERSION) + r"(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?", tag):
        raise ValueError(f"Expected v{VERSION}, optionally followed by a safe release label")


def pack_test_evidence(source, output):
    """Identical test evidence has identical bytes when a publish job is rerun."""
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo("verification/" + path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


def upload_asset(repository, release_id, path):
    """Upload to the known release ID; never rediscover a draft by its tag."""
    with path.open("rb") as stream:
        request = Request(f"https://uploads.github.com/repos/{repository}/releases/{release_id}/assets?name="
                          + quote(path.name, safe=""), data=stream, method="POST", headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/octet-stream",
            "Content-Length": str(path.stat().st_size)})
        # Do not blindly retry a write whose outcome may be unknown. A job rerun
        # discovers the asset and verifies its digest before deciding to upload.
        with urlopen(request, timeout=120) as response:
            return json.load(response)


def verify_assets(local, remote):
    names = {row["name"] for row in remote}
    if len(names) != len(remote) or names != set(local):
        raise ValueError(f"Release asset names differ: {sorted(names ^ set(local))}")
    for asset in remote:
        expected = local[asset["name"]]
        if asset["state"] != "uploaded" or asset["size"] != expected["bytes"] or asset.get("digest") != "sha256:" + expected["sha256"]:
            raise ValueError("Remote asset verification failed: " + asset["name"])


def refresh_release(repository, release_id, local=None, *, published=False):
    """Bounded read-after-write verification, always using the returned ID."""
    last_error = "Release is not yet visible by ID"
    for attempt in range(8):
        release = api(repository, f"releases/{release_id}", missing_ok=True)
        if release is not None:
            if release.get("id") != release_id:
                raise ValueError("GitHub returned a different release ID")
            try:
                if local is not None:
                    verify_assets(local, release["assets"])
                if published and (release["draft"] or release["prerelease"]):
                    raise ValueError("Release publication was not confirmed")
                return release
            except ValueError as error:
                last_error = str(error)
        if attempt < 7:
            time.sleep(2)
    raise ValueError(last_error)


def find_release(repository, tag):
    """Drafts can exist before their Git tag and require the authenticated list."""
    release = api(repository, "releases/tags/" + quote(tag, safe=""), missing_ok=True)
    if release is not None:
        return release
    for page in range(1, 21):
        releases = api(repository, f"releases?per_page=100&page={page}")
        matches = [item for item in releases if item["tag_name"] == tag]
        if len(matches) > 1:
            raise ValueError("More than one release has the requested tag")
        if matches:
            return matches[0]
        if len(releases) < 100:
            return None
    raise ValueError("Release lookup exceeded its bounded pagination limit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--build-origin", type=Path, help="Actions recovery receipt for the original verified build")
    args = parser.parse_args()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        parser.error("Release upload is permitted only by a manual GitHub Actions run on main")
    try:
        validate_tag(args.tag)
    except ValueError as error:
        parser.error(str(error))
    repository, publisher_commit = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    publisher_run_url = f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    commit, run_url = publisher_commit, publisher_run_url
    if args.build_origin:
        from recover_software_release import fetch_build_origin
        saved_origin = json.loads(args.build_origin.read_text(encoding="utf-8"))
        verified_origin = fetch_build_origin(repository, saved_origin["build_run_id"])
        if saved_origin != verified_origin:
            raise ValueError("Build provenance changed after recovery validation")
        commit, run_url = verified_origin["source_commit"], verified_origin["build_actions_run"]
    files = sorted(path for path in args.directory.iterdir() if path.is_file())
    local = {path.name: inspect_archive(path) for path in files}
    manifest = json.loads((args.directory / "SOFTWARE_MANIFEST.json").read_text(encoding="utf-8"))
    if (manifest["source_commit"] != commit or manifest["actions_run"] != run_url or manifest["version"] != VERSION
            or manifest.get("publisher_commit") != publisher_commit
            or manifest.get("publisher_actions_run") != publisher_run_url):
        raise ValueError("The release manifest does not belong to this source commit and Actions run")
    for row in manifest["files"]:
        if row != local.get(row["file"]):
            raise ValueError("Asset changed after manifest creation: " + row["file"])
    if set(local) != {row["file"] for row in manifest["files"]} | {"SOFTWARE_MANIFEST.json", "SHA256SUMS.txt"}:
        raise ValueError("Unexpected files were added to the release directory")
    checksum_names = []
    for line in (args.directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        checksum_names.append(name)
        if name not in local or local[name]["sha256"] != digest:
            raise ValueError("Checksum list does not match: " + name)
    if len(checksum_names) != len(set(checksum_names)) or set(checksum_names) != set(local) - {"SHA256SUMS.txt"}:
        raise ValueError("Checksum list is incomplete or contains duplicates")
    tag = api(repository, "git/ref/tags/" + quote(args.tag, safe=""), missing_ok=True)
    if tag is not None and (tag["object"]["type"] != "commit" or tag["object"]["sha"] != commit):
        raise ValueError("Existing tag belongs to another commit; it will not be moved")
    release = find_release(repository, args.tag)

    if release is not None and ("Build and verification: " + run_url not in release.get("body", "").splitlines()
                                or release["target_commitish"] != commit):
        raise ValueError("An existing release is protected; it will not be overwritten")
    if release is None:
        notes = f"""## MIC-50-90 {VERSION}

MIC-50-90 combines MIC summaries and additional counts to describe compatible MIC distributions, evaluate reporting choices and produce readable local reports.

### Downloads
- **Windows:** extract `MIC-50-90-{VERSION}-Windows-x64.zip` and run `MIC-50-90.exe`.
- **CLI:** install the wheel with `python -m pip install mic_50_90-{VERSION}-py3-none-any.whl`.
- **Source:** `MIC-50-90-{VERSION}-software-source.zip` contains the code, tests, usage documentation, example inputs and build scripts.

The wheel, source distribution and Windows application were built by GitHub Actions from `{commit}`. Release checks include Windows/Linux Python tests, JavaScript form tests, isolated package installation, a packaged Windows analysis compared with CLI, and a real browser form check. The manifests and verification receipts accompany the downloads.

Build and verification: {run_url}
Upload and asset verification: {publisher_run_url}
"""
        release = api(repository, "releases", method="POST", payload={
            "tag_name": args.tag, "target_commitish": commit, "draft": True,
            "prerelease": False, "name": f"MIC-50-90 {VERSION}", "body": notes})
    release_id = release["id"]
    if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
        raise ValueError("GitHub did not return a valid release ID")
    if release["draft"]:
        existing = {asset["name"]: asset for asset in release["assets"]}
        if len(existing) != len(release["assets"]) or set(existing) - set(local):
            raise ValueError("Existing release assets are protected; they will not be replaced")
        for path in files:
            if path.name in existing:
                verify_assets({path.name: local[path.name]}, [existing[path.name]])
            else:
                upload_asset(repository, release_id, path)
        release = refresh_release(repository, release_id, local)
        body = release.get("body", "")
        marker = "Upload and asset verification: "
        body = "\n".join(line for line in body.splitlines() if not line.startswith(marker))
        api(repository, f"releases/{release_id}", method="PATCH", payload={
            "draft": False, "prerelease": False, "make_latest": "true",
            "body": body.rstrip() + "\n\n" + marker + publisher_run_url + "\n"})
    # A rerun after publication may verify the identical release, but it may
    # neither overwrite assets nor mutate an already published release.
    final = refresh_release(repository, release_id, local, published=True)
    final_tag = api(repository, "git/ref/tags/" + quote(args.tag, safe=""))
    if final_tag["object"]["type"] != "commit" or final_tag["object"]["sha"] != commit:
        raise ValueError("Published tag does not identify the verified source commit")
    Path("RELEASE_PUBLICATION.json").write_text(json.dumps({"status": "published_and_verified",
        "release_url": final["html_url"], "source_commit": commit, "actions_run": run_url,
        "publisher_commit": publisher_commit, "publisher_actions_run": publisher_run_url,
        "assets": [{"name": row["name"], "size": row["size"], "digest": row["digest"]} for row in final["assets"]]}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

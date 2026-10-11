"""Release publication must survive stale GitHub reads without replacing assets."""
from copy import deepcopy
from hashlib import sha256
import json
from io import BytesIO
import os
from pathlib import Path
import sys
import subprocess

import pytest


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    import publish_software_release
    return publish_software_release


def setup_run(publisher, monkeypatch, tmp_path, tag="v1.0.0"):
    commit = "a" * 40
    run_url = "https://github.com/owner/project/actions/runs/123"
    directory = tmp_path / "release"
    directory.mkdir()
    asset = directory / "usage.txt"
    asset.write_text("Verified software example\n", encoding="utf-8")
    row = publisher.inspect_archive(asset)
    manifest = {"source_commit": commit, "publisher_commit": commit, "version": "1.0.0",
                "actions_run": run_url, "publisher_actions_run": run_url, "files": [row]}
    (directory / "SOFTWARE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "SHA256SUMS.txt").write_text("".join(
        f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(directory.iterdir())), encoding="utf-8")
    for key, value in {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                       "GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": "owner/project",
                       "GITHUB_SHA": commit, "GITHUB_RUN_ID": "123"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["publisher", "--directory", str(directory), "--tag", tag])
    monkeypatch.chdir(tmp_path)
    return directory, {"id": 42, "tag_name": tag, "target_commitish": commit, "draft": True,
                       "prerelease": False, "body": "Build and verification: " + run_url,
                       "assets": [], "html_url": "https://github.com/owner/project/releases/tag/" + tag}


def fake_remote(publisher, monkeypatch, draft, *, initial=False, delay_assets=False):
    """Emulate only remote API/transport; execute the publisher and file checks."""
    state = {"release": deepcopy(draft) if initial else None, "mutations": [], "reads": [], "stale": 0}

    def api(repository, path, *, missing_ok=False, method="GET", payload=None):
        assert repository == "owner/project"
        if method != "GET":
            state["mutations"].append((method, path, deepcopy(payload)))
        if method == "POST" and path == "releases":
            state["release"] = deepcopy(draft)
            return deepcopy(state["release"])
        if method == "PATCH" and path == "releases/42":
            state["release"].update(payload)
            return deepcopy(state["release"])
        if path.startswith("git/ref/tags/"):
            return {"object": {"type": "commit", "sha": "a" * 40}} if state["release"] and not state["release"]["draft"] else None
        if path.startswith("releases/tags/"):
            # A newly created draft is deliberately NEVER discoverable by tag.
            return deepcopy(state["release"]) if initial else None
        if path.startswith("releases?"):
            return []
        if path == "releases/42":
            state["reads"].append(path)
            result = deepcopy(state["release"])
            if delay_assets and state["stale"] < 2:
                result["assets"] = []
                state["stale"] += 1
            return result
        raise AssertionError((method, path))

    def upload(repository, release_id, path):
        assert release_id == 42
        state["mutations"].append(("UPLOAD", path.name))
        state["release"]["assets"].append({"name": path.name, "size": path.stat().st_size,
            "digest": "sha256:" + sha256(path.read_bytes()).hexdigest(), "state": "uploaded"})

    monkeypatch.setattr(publisher, "api", api)
    # Network calls are never made by these tests.
    monkeypatch.setattr(publisher, "upload_asset", upload, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Publication must use the returned release ID, not gh tag lookup")))
    if hasattr(publisher, "time"):
        monkeypatch.setattr(publisher.time, "sleep", lambda _: None)
    return state


def test_new_draft_uses_returned_id_despite_stale_tag_listing(publisher, monkeypatch, tmp_path):
    _, draft = setup_run(publisher, monkeypatch, tmp_path, tag="v1.0.0-code-20261007")
    state = fake_remote(publisher, monkeypatch, draft, delay_assets=True)
    publisher.main()
    receipt = json.loads((tmp_path / "RELEASE_PUBLICATION.json").read_text())
    assert receipt["status"] == "published_and_verified"
    assert len(receipt["assets"]) == 3
    assert state["reads"] == ["releases/42"] * 4
    assert state["release"]["draft"] is False


def test_partial_draft_resumes_without_replacing_existing_asset(publisher, monkeypatch, tmp_path):
    directory, draft = setup_run(publisher, monkeypatch, tmp_path)
    path = directory / "usage.txt"
    draft["assets"] = [{"name": path.name, "size": path.stat().st_size,
                        "digest": "sha256:" + sha256(path.read_bytes()).hexdigest(), "state": "uploaded"}]
    state = fake_remote(publisher, monkeypatch, draft, initial=True)
    publisher.main()
    assert ("UPLOAD", "usage.txt") not in state["mutations"]
    assert sum(item[0] == "UPLOAD" for item in state["mutations"]) == 2


def test_same_run_published_release_is_verified_without_mutation(publisher, monkeypatch, tmp_path):
    directory, draft = setup_run(publisher, monkeypatch, tmp_path)
    draft["draft"] = False
    draft["assets"] = [{"name": path.name, "size": path.stat().st_size,
                        "digest": "sha256:" + sha256(path.read_bytes()).hexdigest(), "state": "uploaded"}
                       for path in directory.iterdir()]
    state = fake_remote(publisher, monkeypatch, draft, initial=True)
    publisher.main()
    assert state["mutations"] == []
    assert (tmp_path / "RELEASE_PUBLICATION.json").is_file()


@pytest.mark.parametrize("change", [{"body": "another run"}, {"target_commitish": "b" * 40}])
def test_foreign_release_is_protected(publisher, monkeypatch, tmp_path, change):
    _, draft = setup_run(publisher, monkeypatch, tmp_path)
    draft.update(change)
    state = fake_remote(publisher, monkeypatch, draft, initial=True)
    with pytest.raises(ValueError, match="protected"):
        publisher.main()
    assert state["mutations"] == []


@pytest.mark.parametrize("tag", ["v1.0.0", "v1.0.0-code-20261007", "v1.0.0-review.2"])
def test_fixed_version_tag_and_safe_labels_are_accepted(publisher, tag):
    publisher.validate_tag(tag)


@pytest.mark.parametrize("tag", ["v1.0.1", "v1.0.01", "v1.0.0/other", "v1.0.0-..", "v1.0.0-", "v1.0.0-$(cmd)"])
def test_other_versions_and_unsafe_tags_are_rejected(publisher, tag):
    with pytest.raises(ValueError):
        publisher.validate_tag(tag)


def test_incomplete_remote_assets_stop_before_publication(publisher, monkeypatch, tmp_path):
    _, draft = setup_run(publisher, monkeypatch, tmp_path)
    state = fake_remote(publisher, monkeypatch, draft)
    monkeypatch.setattr(publisher, "upload_asset", lambda *args: None)
    with pytest.raises(ValueError, match="asset"):
        publisher.main()
    assert state["release"]["draft"] is True
    assert not any(item[0] == "PATCH" for item in state["mutations"])


def test_test_archive_is_identical_after_file_time_changes(publisher, tmp_path):
    source = tmp_path / "verification"
    source.mkdir()
    report = source / "test.xml"
    report.write_text('<testsuite tests="1" failures="0"/>', encoding="utf-8")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    publisher.pack_test_evidence(source, first)
    os.utime(report, (1735689600, 1735689600))
    publisher.pack_test_evidence(source, second)
    assert first.read_bytes() == second.read_bytes()


def test_creation_posts_json_and_keeps_the_returned_release_id(publisher, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "test-token")
    requests = []

    def transport(request, **kwargs):
        requests.append(request)
        return BytesIO(b'{"id":42,"draft":true,"assets":[]}')

    monkeypatch.setattr(publisher, "urlopen", transport)
    result = publisher.api("owner/project", "releases", method="POST",
                           payload={"tag_name": "v1.0.0", "draft": True})
    assert result["id"] == 42
    assert requests[0].method == "POST"
    assert json.loads(requests[0].data) == {"tag_name": "v1.0.0", "draft": True}


def test_upload_streams_to_release_id_without_tag_lookup(publisher, monkeypatch, tmp_path):
    monkeypatch.setenv("GH_TOKEN", "test-token")
    path = tmp_path / "package.zip"
    path.write_bytes(b"test content")
    requests = []

    def transport(request, **kwargs):
        requests.append((request.full_url, request.method, request.data.read(), request.get_header("Content-length")))
        return BytesIO(b'{"name":"package.zip","state":"uploaded"}')

    monkeypatch.setattr(publisher, "urlopen", transport)
    publisher.upload_asset("owner/project", 42, path)
    assert requests == [("https://uploads.github.com/repos/owner/project/releases/42/assets?name=package.zip",
                         "POST", b"test content", "12")]

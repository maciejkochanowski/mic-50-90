"""Publication files must never enter the software release, including nested ZIPs."""
from io import BytesIO
import importlib.util
from pathlib import Path
import tarfile
import zipfile
import sys

import pytest

_path = Path(__file__).resolve().parents[1] / "tools/software_release.py"
_spec = importlib.util.spec_from_file_location("software_release_test", _path)
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


@pytest.mark.parametrize("name", ["manuscript/main.md", "Main.PDF", "Appendix-A.pdf", "supplements/a.md", "../outside", "manual.docx", "scripts/build_validation_notebook.py"])
def test_publication_paths_are_rejected(name):
    with pytest.raises(ValueError):
        release.check_name(name)


def test_usage_documentation_remains_allowed(tmp_path):
    source = tmp_path / "software.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("docs/GUI_GUIDE.md", "# Using MIC-50-90\nOpen the program.")
        archive.writestr("src/mic_50_90/cli.py", "print('hello')")
    assert release.inspect_archive(source)["status"] == "passed"


def test_hpc_folder_is_excluded_from_distributed_source(tmp_path):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("MIC-50-90-1.0.0/hpc/slurm.sh", "#!/bin/sh\necho cluster-only\n")
        archive.writestr("MIC-50-90-1.0.0/src/mic_50_90/cli.py", "print('hello')")
    with pytest.raises(ValueError, match="hpc"):
        release.inspect_archive(source)


def test_nested_article_is_rejected(tmp_path):
    inner = BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("main.pdf", b"%PDF-1.7")
    outer = tmp_path / "software.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("renamed.dat", inner.getvalue())
    with pytest.raises(ValueError):
        release.inspect_archive(outer)


def test_renamed_pdf_is_rejected(tmp_path):
    source = tmp_path / "release.data"
    source.write_bytes(b"%PDF-1.7\n")
    with pytest.raises(ValueError):
        release.inspect_archive(source)


def test_source_tar_with_article_is_rejected(tmp_path):
    source = tmp_path / "software.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        content = b"full article"
        info = tarfile.TarInfo("package/manuscript/main.md")
        info.size = len(content)
        archive.addfile(info, BytesIO(content))
    with pytest.raises(ValueError):
        release.inspect_archive(source)


def test_archive_link_is_rejected(tmp_path):
    source = tmp_path / "software.zip"
    with zipfile.ZipFile(source, "w") as archive:
        info = zipfile.ZipInfo("docs/link")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "outside")
    with pytest.raises(ValueError):
        release.inspect_archive(source)


def test_publisher_requires_actions(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(_path.parent))
    import publish_software_release as publisher
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(sys, "argv", ["publisher", "--directory", str(tmp_path), "--tag", "v1.0.0-code-20261007"])
    with pytest.raises(SystemExit):
        publisher.main()


@pytest.mark.parametrize("change", [{"size": 2}, {"digest": "sha256:other"}, {"state": "new"}, {"name": "other.whl"}])
def test_remote_release_mismatch_is_rejected(monkeypatch, change):
    monkeypatch.syspath_prepend(str(_path.parent))
    import publish_software_release as publisher
    local = {"package.whl": {"bytes": 1, "sha256": "correct"}}
    remote = {"name": "package.whl", "size": 1, "digest": "sha256:correct", "state": "uploaded", **change}
    with pytest.raises(ValueError):
        publisher.verify_assets(local, [remote])


def test_draft_without_git_tag_is_found_from_authenticated_list(monkeypatch):
    monkeypatch.syspath_prepend(str(_path.parent))
    import publish_software_release as publisher
    draft = {"id": 12, "tag_name": "v1", "draft": True}
    monkeypatch.setattr(publisher, "api", lambda repo, path, **kwargs: None if path.startswith("releases/tags/") else [draft])
    assert publisher.find_release("owner/project", "v1") == draft


def test_missing_release_stays_missing(monkeypatch):
    monkeypatch.syspath_prepend(str(_path.parent))
    import publish_software_release as publisher
    monkeypatch.setattr(publisher, "api", lambda repo, path, **kwargs: None if path.startswith("releases/tags/") else [])
    assert publisher.find_release("owner/project", "v1") is None

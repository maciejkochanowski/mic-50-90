"""The portable application must carry the licence of its own software."""
from pathlib import Path
import importlib.util
import shutil
import sys

import pytest


def builder():
    path = Path(__file__).resolve().parents[1] / "tools/build_windows.py"
    spec = importlib.util.spec_from_file_location("windows_licence_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(tmp_path):
    root = tmp_path / "source"
    for name, content in {
        "LICENSE": "MIT License\nCopyright example\n",
        "NOTICE.md": "Third-party fonts retain their licences.\n",
        "pyproject.toml": "[project]\nversion = '1.0.0'\n",
        "tools/build_windows.py": "# builder\n",
        "tools/desktop_launcher.py": "# launcher\n",
        "src/mic_50_90/gui_assets/example.txt": "resource\n",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_portable_build_carries_licence_and_notice(tmp_path, monkeypatch):
    module = builder()
    root = source(tmp_path)
    output = tmp_path / "build"
    monkeypatch.setattr(module, "__file__", str(root / "tools/build_windows.py"))
    monkeypatch.setattr(sys, "argv", ["build_windows.py", "--output", str(output)])
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(module.importlib.metadata, "version", lambda _: "test")

    def freeze(command, **kwargs):
        app = output / "application/MIC-50-90"
        shutil.copytree(root / "src/mic_50_90/gui_assets", app / "_internal/mic_50_90/gui_assets")
        (app / "MIC-50-90.exe").write_bytes(b"test application")

    monkeypatch.setattr(module.subprocess, "run", freeze)
    module.main()
    app = output / "application/MIC-50-90"
    for name in ("LICENSE", "NOTICE.md"):
        assert (app / name).read_bytes() == (root / name).read_bytes()


def test_licence_change_invalidates_build_source_identity(tmp_path):
    module = builder()
    root = source(tmp_path)
    identity = module.source_identity(root)
    (root / "LICENSE").write_text("Changed licence\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="LICENSE"):
        module.verify_source_identity(root, identity)

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
        "LICENSE.txt": "MIT License\nCopyright example\n",
        "NOTICE.md": "Third-party fonts retain their licences.\n",
        "pyproject.toml": "[project]\nversion = '1.0.1'\n",
        "tools/build_windows.py": "# builder\n",
        "tools/desktop_launcher.py": "# launcher\n",
        "tools/release_version.py": "# version helper\n",
        "src/mic_50_90/_version.py": '__version__ = "1.0.1"\n',
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
    for name in ("LICENSE.txt", "NOTICE.md"):
        assert (app / name).read_bytes() == (root / name).read_bytes()


def test_licence_change_invalidates_build_source_identity(tmp_path):
    module = builder()
    root = source(tmp_path)
    identity = module.source_identity(root)
    (root / "LICENSE.txt").write_text("Changed licence\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="LICENSE.txt"):
        module.verify_source_identity(root, identity)


def test_version_mismatch_is_rejected_before_build(tmp_path, monkeypatch):
    module = builder()
    root = source(tmp_path)
    (root / "src/mic_50_90/_version.py").write_text('__version__="1.0.2"\n')
    output = tmp_path / "build"
    monkeypatch.setattr(module, "__file__", str(root / "tools/build_windows.py"))
    monkeypatch.setattr(sys, "argv", ["build_windows.py", "--output", str(output)])
    monkeypatch.setattr(sys, "platform", "win32")
    def do_not_build(*args, **kwargs):
        raise AssertionError("The builder ran before version validation")
    monkeypatch.setattr(module.subprocess, "run", do_not_build)
    with pytest.raises(ValueError, match="versions do not match"):
        module.main()
    assert not output.exists()

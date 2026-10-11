"""One explicit source-delivery file selection shared by manifest and bundle tools.

Runtime resources are selected by directory, never by a Python-only glob. Historical
campaigns and generated archives retain their own manifests; they are not recursively
folded into the current source identity.
"""
from __future__ import annotations

from pathlib import Path

ROOT_FILES = (
    "README.md", "README_REVIEWER.md", "DELIVERY.md", "PACKAGE_STATUS.json",
    "pyproject.toml", "LICENSE", "NOTICE.md", "SECURITY.md",
    "CONTRIBUTING.md", "CITATION.cff", "CHANGELOG.md", "codemeta.json",
    ".zenodo.json", ".gitignore", ".gitattributes", "uv.lock", "Dockerfile", ".dockerignore",
    "verify.sh", "reproducibility/self_test.py",
    "data/SOURCES.md", "data/LICENSES.md",
)
SOURCE_DIRECTORIES = (
    "src", "tests", "schemas", "examples", "docs", "formal", "scripts", "reproducibility",
    ".github/workflows", "tools",
)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git", ".venv", "node_modules", ".lake"}


def source_files(root: Path) -> list[Path]:
    root = root.resolve()
    files = {root / name for name in ROOT_FILES if (root / name).is_file()}
    for directory in SOURCE_DIRECTORIES:
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if (path.is_file() and not EXCLUDED_PARTS.intersection(relative.parts)
                    and path.suffix not in {".pyc", ".pyo"}):
                files.add(path)
    # Editorial sources and their numerical claim maps never enter a software bundle.
    forbidden_parts = {"manuscript", "manuscripts", "article", "supplement", "supplements",
                       "appendices", "supplementary-appendices", "technical-archive"}
    def permitted(path):
        rel = path.relative_to(root)
        return not (forbidden_parts.intersection(part.lower() for part in rel.parts)
                    or rel.as_posix().startswith("tools/publication/")
                    or path.name.startswith("MIC-50-90-main-")
                    or ("MIC-50-90-" in path.name and "-Appendix-" in path.name)
                    or (path.name.startswith(("manuscript_claims_", "appendix_")) and "claims" in path.name))
    return sorted((p for p in files if permitted(p)), key=lambda path: path.relative_to(root).as_posix())

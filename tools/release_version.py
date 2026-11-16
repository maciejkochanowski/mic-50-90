"""Read the declared version without importing numerical runtime dependencies."""
from __future__ import annotations
import ast
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def read_version(root: Path = ROOT) -> str:
    version = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    tree = ast.parse((root/'src/mic_50_90/_version.py').read_text(encoding='utf-8'))
    declared = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
    if declared != [version]:
        raise ValueError('Package metadata and runtime versions do not match')
    if not isinstance(version, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version):
        raise ValueError('Release tooling requires a three-part final version')
    return version


if __name__ == '__main__':
    print(read_version())

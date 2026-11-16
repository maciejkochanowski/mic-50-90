"""Collect and execute the complete suite against one installed wheel.

No test selectors are accepted. The independently collected manifest is reused
by every matrix job; reports record exact node IDs and artifact provenance.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import pytest

from check_release_tests import MANIFEST_SCHEMA, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def source_identity(root: Path = ROOT) -> str:
    # Use the same file selection as the delivered source manifest. Generated
    # logs/wheels live outside these directories and cannot change this digest.
    sys.path.insert(0, str(root / 'scripts'))
    try:
        from package_files import source_files
        rows = [(p.relative_to(root).as_posix(), sha256(p.read_bytes()).hexdigest())
                for p in source_files(root)]
    finally:
        sys.path.pop(0)
    return sha256(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def installed_identity(wheel: Path, root: Path = ROOT) -> dict:
    import mic_50_90
    package = Path(mic_50_90.__file__).resolve().parent
    if package.is_relative_to(root.resolve()):
        raise ValueError('Tests must import the installed wheel, not checkout sources')
    if wheel.is_symlink() or not wheel.is_file():
        raise ValueError('Expected a regular wheel file')
    expected = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if not name.startswith('mic_50_90/') or name.endswith('/'):
                continue
            rel = Path(name.removeprefix('mic_50_90/'))
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Unsafe path in wheel')
            expected[rel.as_posix()] = sha256(archive.read(name)).hexdigest()
    actual = {p.relative_to(package).as_posix(): sha256(p.read_bytes()).hexdigest()
              for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts
              and p.suffix not in {'.pyc', '.pyo'}}
    if not expected or actual != expected:
        raise ValueError('Installed runtime files differ from the specified wheel')
    return {'installed_package': str(package), 'runtime_files_checked': len(expected),
            'wheel_sha256': sha256(wheel.read_bytes()).hexdigest(),
            'source_tree_sha256': source_identity(root)}


class EvidencePlugin:
    def __init__(self, expected_ids=None):
        self.test_ids = []
        self.expected_ids = None if expected_ids is None else set(expected_ids)
        self.deselected = False
        self.collection_skips = []

    def pytest_collectreport(self, report):
        if report.skipped:
            self.collection_skips.append(report.nodeid)

    def pytest_deselected(self, items):
        if items:
            self.deselected = True

    def pytest_collection_finish(self, session):
        if self.collection_skips:
            raise pytest.UsageError(
                "Release evidence forbids collection-time skips: "
                + ", ".join(self.collection_skips))
        if self.deselected:
            raise pytest.UsageError('Release evidence must not use filtered/deselected tests')
        self.test_ids = [item.nodeid for item in session.items]
        if len(self.test_ids) != len(set(self.test_ids)):
            raise pytest.UsageError('Duplicate collected test IDs')
        if self.expected_ids is not None and set(self.test_ids) != self.expected_ids:
            raise pytest.UsageError('Collected IDs differ from the frozen expected manifest')
        for item in session.items:
            item.user_properties.append(('mic_50_90_nodeid', item.nodeid))


def _write_json_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(data, indent=2, ensure_ascii=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('collect', 'run'))
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, help='Manifest output for collect')
    parser.add_argument('--manifest', type=Path, help='Frozen manifest for run')
    parser.add_argument('--junit', type=Path, help='JUnit output for run')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        parser.error('Use the full source commit')
    if os.environ.get('PYTEST_ADDOPTS'):
        parser.error('PYTEST_ADDOPTS must be unset for unfiltered release evidence')
    target = args.output if args.mode == 'collect' else args.junit
    if target is None or target.exists():
        parser.error('Use a new --output (collect) or --junit (run) path')
    args.wheel = args.wheel.resolve()
    target = target.resolve()
    try:
        before = installed_identity(args.wheel)
        expected = None
        manifest_sha = None
        if args.mode == 'run':
            if args.manifest is None:
                parser.error('--manifest is required for run')
            expected = load_manifest(args.manifest, args.commit)
            manifest_sha = sha256(args.manifest.read_bytes()).hexdigest()
            for key in ('source_tree_sha256', 'wheel_sha256'):
                if expected[key] != before[key]:
                    raise ValueError('Run identity differs from the frozen manifest: ' + key)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    os.chdir(ROOT)
    plugin = EvidencePlugin(None if expected is None else expected['test_ids'])
    command = ['tests', '-q', '-ra', '--strict-markers', '-o', 'addopts=', '-o', 'junit_family=xunit1']
    if args.mode == 'collect':
        command.append('--collect-only')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        command.append('--junitxml=' + str(target))
    code = int(pytest.main(command, plugins=[plugin]))
    try:
        after = installed_identity(args.wheel)
        if after != before:
            raise ValueError('Source or installed runtime changed during testing')
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        code = code or 1
    identity = {key: before[key] for key in ('source_tree_sha256', 'wheel_sha256')}
    identity['source_commit'] = args.commit
    if args.mode == 'collect':
        if code == 0 and plugin.test_ids:
            # Only explicitly platform-specific files can ever receive a
            # separately reviewed per-job exception; all other tests are core.
            protected = [n for n in plugin.test_ids if not n.startswith(
                ('tests/test_platform_', 'tests/test_windows_'))]
            _write_json_new(target, {'schema': MANIFEST_SCHEMA, **identity,
                'test_ids': plugin.test_ids, 'non_skippable_test_ids': protected})
        return code or (0 if plugin.test_ids else 5)
    if target.is_file():
        tree = ET.parse(target)
        suites = list(tree.getroot().iter('testsuite'))
        if len(suites) != 1:
            return code or 1
        suite = suites[0]
        properties = ET.SubElement(suite, 'properties')
        for name, value in {**identity, 'test_manifest_sha256': manifest_sha, 'runner_exit_code': str(code),
                'platform': platform.system(), 'python_version': f'{sys.version_info.major}.{sys.version_info.minor}'}.items():
            ET.SubElement(properties, 'property', name=name, value=value)
        tree.write(target, encoding='utf-8', xml_declaration=True)
    _write_json_new(target.with_suffix('.runtime.json'), {**identity, **before,
        'python': sys.version, 'platform': platform.platform(), 'runner_exit_code': code,
        'versions': {name: importlib.metadata.version(name) for name in
                     ('numpy', 'scipy', 'pytest', 'hypothesis', 'jsonschema')},
        'junit_sha256': sha256(target.read_bytes()).hexdigest() if target.is_file() else None})
    return code


if __name__ == '__main__':
    raise SystemExit(main())

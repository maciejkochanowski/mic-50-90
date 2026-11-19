"""Release guards: completeness, identity, consent and compatible saved formats."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'a' * 40
IDENTITY = {'source_commit': COMMIT, 'source_tree_sha256': 'b' * 64, 'wheel_sha256': 'c' * 64}
TEST_IDS = ['tests/test_platform_checks.py::test_one', 'tests/test_input_and_numerical_contracts.py::test_core']


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proof(root, *, test_ids=None, skipped=(), report_identity=None):
    tool = load_tool('check_release_tests')
    manifest = {"schema": "mic-50-90.test-manifest/1", **IDENTITY,
                'test_ids': TEST_IDS, 'non_skippable_test_ids': [TEST_IDS[1]]}
    path = root / 'expected-tests.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    props = {**IDENTITY, 'test_manifest_sha256': sha256(path.read_bytes()).hexdigest(),
             'runner_exit_code': '0', **(report_identity or {})}
    ids = TEST_IDS if test_ids is None else test_ids
    for job in sorted(tool.EXPECTED):
        parent = root / job
        parent.mkdir()
        suite = ET.Element('testsuite', tests=str(len(ids)), failures='0', errors='0',
                           skipped=str(sum(t in skipped for t in ids)), time='1.5')
        properties = ET.SubElement(suite, 'properties')
        values = {**props, 'platform': 'Windows' if 'windows' in job else 'Linux',
                  'python_version': job.rsplit('-', 1)[1]}
        for key, value in values.items():
            ET.SubElement(properties, 'property', name=key, value=value)
        for ident in ids:
            case = ET.SubElement(suite, 'testcase', classname=ident.split('::')[0], name=ident.split('::')[-1])
            p = ET.SubElement(case, 'properties')
            ET.SubElement(p, 'property', name='mic_50_90_nodeid', value=ident)
            if ident in skipped:
                ET.SubElement(case, 'skipped', message='platform condition')
        ET.ElementTree(suite).write(parent / 'test-results.xml', encoding='utf-8')
    return tool, path


def verify(tool, root, manifest, **kwargs):
    return tool.verify_matrix(root, manifest=manifest, expected_commit=COMMIT, **kwargs)


def test_complete_identified_matrix(tmp_path):
    tool, manifest = proof(tmp_path)
    result = verify(tool, tmp_path, manifest)
    assert result['status'] == 'passed'
    assert result['source_commit'] == COMMIT
    assert all(row['executed'] == 2 for row in result['checks'])


def test_one_executed_and_many_skipped_is_not_release_evidence(tmp_path):
    tool, manifest = proof(tmp_path, skipped=[TEST_IDS[1]])
    with pytest.raises(ValueError, match='skip'):
        verify(tool, tmp_path, manifest)


def test_identical_incomplete_reports_are_rejected(tmp_path):
    tool, manifest = proof(tmp_path, test_ids=[TEST_IDS[0]])
    with pytest.raises(ValueError, match='expected|manifest'):
        verify(tool, tmp_path, manifest)


@pytest.mark.parametrize('field,bad', [('source_commit', 'd'*40), ('source_tree_sha256', 'd'*64),
    ('wheel_sha256', 'd'*64), ('test_manifest_sha256', 'd'*64), ('runner_exit_code', '2')])
def test_wrong_report_provenance_is_rejected(tmp_path, field, bad):
    tool, manifest = proof(tmp_path, report_identity={field: bad})
    with pytest.raises(ValueError, match='identity|provenance|runner'):
        verify(tool, tmp_path, manifest)


def test_wrong_manifest_revision_is_rejected(tmp_path):
    tool, manifest = proof(tmp_path)
    with pytest.raises(ValueError, match='commit|revision'):
        tool.verify_matrix(tmp_path, manifest=manifest, expected_commit='e'*40)


def test_duplicate_test_is_rejected(tmp_path):
    tool, manifest = proof(tmp_path, test_ids=[TEST_IDS[0], TEST_IDS[0]])
    with pytest.raises(ValueError, match='Duplicate'):
        verify(tool, tmp_path, manifest)


def test_missing_manifest_is_not_an_optional_check(tmp_path):
    tool, manifest = proof(tmp_path)
    manifest.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(tool, tmp_path, manifest)


def test_explicit_narrow_platform_exception_is_recorded(tmp_path):
    tool, manifest = proof(tmp_path)
    job = 'verification-windows-latest-3.11'
    xml = tmp_path / job / 'test-results.xml'
    tree = ET.parse(xml); suite = tree.getroot(); suite.set('skipped', '1')
    ET.SubElement(suite.findall('testcase')[0], 'skipped', message='reviewed platform condition')
    tree.write(xml, encoding='utf-8')
    policy = tmp_path / 'skips.json'
    policy.write_text(json.dumps({'schema': 'mic-50-90.test-skips/1', 'source_commit': COMMIT,
        'allow': [{'job': job, 'test_id': TEST_IDS[0], 'reason': 'Known platform-only operation'}]}))
    result = verify(tool, tmp_path, manifest, skip_policy=policy)
    row = next(r for r in result['checks'] if r['platform'] == job)
    assert row['skipped'] == 1 and row['executed'] == 1
    assert row['allowed_skips'][0]['reason'] == 'Known platform-only operation'


def test_core_tests_cannot_be_whitelisted(tmp_path):
    tool, manifest = proof(tmp_path, skipped=[TEST_IDS[1]])
    policy = tmp_path / 'skips.json'
    policy.write_text(json.dumps({'schema': 'mic-50-90.test-skips/1', 'source_commit': COMMIT,
        'allow': [{'job': job, 'test_id': TEST_IDS[1], 'reason': 'not a valid exception'} for job in tool.EXPECTED]}))
    with pytest.raises(ValueError, match='protected|required|non.skippable'):
        verify(tool, tmp_path, manifest, skip_policy=policy)


def test_publication_requires_an_independent_approval(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT/'tools'))
    import publish_software_release as publisher
    for key,value in {'GITHUB_ACTIONS':'true', 'GITHUB_EVENT_NAME':'workflow_dispatch',
                      'GITHUB_REF':'refs/heads/main'}.items():monkeypatch.setenv(key,value)
    monkeypatch.delenv('MIC50_90_PUBLISH_APPROVED', raising=False)
    monkeypatch.setattr(sys,'argv',['publisher','--directory',str(tmp_path),'--tag','v1.0.1'])
    with pytest.raises(SystemExit) as error:publisher.main()
    assert error.value.code == 2


def test_publication_switch_is_false_by_default_and_gates_both_destinations():
    text = (ROOT/'.github/workflows/release.yml').read_text()
    assert 'publish_github:' in text
    section = text.split('publish_github:',1)[1].split('publish_pypi:',1)[0]
    assert 'default: false' in section
    jobs = text.split('\n  publish:',1)[1]
    assert 'inputs.publish_github' in jobs.split('steps:',1)[0]
    assert 'inputs.publish_github' in text.split('\n  pypi:',1)[1].split('steps:',1)[0]
    assert 'MIC50_90_PUBLISH_APPROVED' in jobs


def test_validation_workflow_has_no_publishing_capability():
    text = (ROOT/'.github/workflows/tests.yml').read_text()
    assert 'contents: read' in text
    assert 'contents: write' not in text and 'id-token: write' not in text
    assert 'publish_software_release.py' not in text
    assert 'run_test_evidence.py' in text and 'check_release_tests.py' in text
    assert 'check_release_archives.py' in text


@pytest.mark.parametrize('version,schema', [('1.0.0',None),('1.0.0','mic-50-90.distribution/1')])
def test_version_100_distribution_identity_is_read_without_mutation(version,schema):
    from mic_50_90.result_schema import validate_distribution_schema
    data={'software':'MIC-50-90','software_version':version}
    if schema:data['result_schema']=schema
    before=deepcopy(data)
    validate_distribution_schema(data)
    assert data==before


@pytest.mark.parametrize('version,schema,software', [('9.9.9','mic-50-90.distribution/1','MIC-50-90'),
    ('9.9.9',None,'MIC-50-90'),('1.0.0','unknown/999','MIC-50-90'),('1.0.0',None,'other')])
def test_unknown_results_are_not_silently_accepted(version,schema,software):
    from mic_50_90.result_schema import validate_distribution_schema
    data={'software':software,'software_version':version}
    if schema:data['result_schema']=schema
    with pytest.raises(ValueError):validate_distribution_schema(data)


def test_current_version_requires_explicit_schema(monkeypatch):
    from mic_50_90 import _version
    from mic_50_90.result_schema import validate_distribution_schema
    monkeypatch.setattr(_version,'__version__','1.0.1')
    data={'software':'MIC-50-90','software_version':'1.0.1','result_schema':'mic-50-90.distribution/1'}
    validate_distribution_schema(data)
    del data['result_schema']
    with pytest.raises(ValueError):validate_distribution_schema(data)


def test_output_contract_schema_is_not_pinned_to_producer_patch_version():
    import jsonschema
    schema=json.loads((ROOT/'schemas/output.schema.json').read_text())['properties']['version']
    jsonschema.Draft202012Validator(schema).validate('1.0.1')
    with pytest.raises(jsonschema.ValidationError):jsonschema.Draft202012Validator(schema).validate('not a version')

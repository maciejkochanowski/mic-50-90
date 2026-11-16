"""The evidence runner must collect independently and bind execution to installed bytes."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_collection_and_junit_keep_exact_node_ids(tmp_path):
    (tmp_path/'test_example.py').write_text('import pytest\n@pytest.mark.parametrize("value", [1, 2])\ndef test_ok(value):\n    assert value > 0\n')
    script = '''
import json,sys,pytest
sys.path.insert(0, sys.argv[1])
from run_test_evidence import EvidencePlugin
plugin=EvidencePlugin()
code=pytest.main(['-q', '--junitxml=out.xml','-o','junit_family=xunit1'], plugins=[plugin])
open('collected.json','w').write(json.dumps(plugin.test_ids))
sys.exit(code)
'''
    process=subprocess.run([sys.executable,'-c',script,str(ROOT/'tools')],cwd=tmp_path,capture_output=True,text=True)
    assert process.returncode==0, process.stdout+process.stderr
    ids=json.loads((tmp_path/'collected.json').read_text())
    assert ids==['test_example.py::test_ok[1]','test_example.py::test_ok[2]']
    cases=ET.parse(tmp_path/'out.xml').findall('.//testcase')
    assert [c.find("./properties/property[@name='mic_50_90_nodeid']").get('value') for c in cases]==ids


def test_runner_rejects_filtered_collection(tmp_path):
    (tmp_path/'test_example.py').write_text('def test_one(): pass\ndef test_two(): pass\n')
    script='''
import sys,pytest
sys.path.insert(0, sys.argv[1])
from run_test_evidence import EvidencePlugin
sys.exit(pytest.main(['--collect-only','-q','-k','test_one'],plugins=[EvidencePlugin()]))
'''
    p=subprocess.run([sys.executable,'-c',script,str(ROOT/'tools')],cwd=tmp_path,capture_output=True,text=True)
    assert p.returncode!=0
    assert 'filtered' in p.stdout+p.stderr or 'deselect' in p.stdout+p.stderr


def test_import_failure_cannot_produce_valid_collection(tmp_path):
    (tmp_path/'test_bad.py').write_text('raise ImportError("deliberate collection failure")\n')
    script='''
import sys,pytest
sys.path.insert(0, sys.argv[1])
from run_test_evidence import EvidencePlugin
sys.exit(pytest.main(['--collect-only','-q'],plugins=[EvidencePlugin()]))
'''
    p=subprocess.run([sys.executable,'-c',script,str(ROOT/'tools')],cwd=tmp_path,capture_output=True,text=True)
    assert p.returncode!=0 and 'deliberate collection failure' in p.stdout+p.stderr


def test_package_version_single_source_agrees_and_detects_mismatch(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'tools'))
    from release_version import read_version
    import tomllib
    assert read_version(ROOT)==tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    (tmp_path/'src/mic_50_90').mkdir(parents=True)
    (tmp_path/'src/mic_50_90/_version.py').write_text('__version__="1.0.1"\n')
    (tmp_path/'pyproject.toml').write_text('[project]\nversion="1.0.0"\n')
    with pytest.raises(ValueError,match='match'):read_version(tmp_path)


@pytest.mark.parametrize("skip_statement", [
    'pytest.skip("module intentionally omitted", allow_module_level=True)',
    'pytest.importorskip("missing_dependency_for_evidence_regression")',
])
def test_collection_time_module_skip_cannot_shrink_manifest(tmp_path, skip_statement):
    (tmp_path/'test_present.py').write_text('def test_ok(): pass\n')
    (tmp_path/'test_hidden.py').write_text('import pytest\n'+skip_statement+'\ndef test_hidden(): pass\n')
    script = """
import sys,pytest
sys.path.insert(0, sys.argv[1])
from run_test_evidence import EvidencePlugin
sys.exit(pytest.main(['--collect-only', '-q'], plugins=[EvidencePlugin()]))
"""
    result = subprocess.run([sys.executable, '-c', script, str(ROOT/'tools')],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'collection-time skip' in result.stdout + result.stderr

"""Public CSV routes exercise preparation bindings and returned counts."""
import copy
import csv
import json
from pathlib import Path

import pytest

from mic_50_90.cli import main
from mic_50_90.calibration_preparation import prepare_calibration


EXAMPLE = Path(__file__).resolve().parents[1]/"examples"/"calibration_preparation"


@pytest.fixture(scope="module")
def prepared():
    return prepare_calibration(EXAMPLE/"counts.csv", panels_path=EXAMPLE/"panels.csv",
        roster_path=EXAMPLE/"roster.csv", metadata_path=EXAMPLE/"metadata.json", level=.75)


def test_prepared_binding_matches_actual_input_geometry_and_identity(prepared):
    from mic_50_90.calibration_binding import validate_prepared_calibration
    assert prepared["status"] == "ready"
    for cid, mapping in prepared["calibrations"].items():
        binding = mapping["calibration_context"]["preparation_binding"]
        panel = prepared["configuration"]["panels"][binding["panel_id"]]
        raw = dict(contract_version="1.0", mode="empirical", n=10, panel=panel,
            summaries={"quantiles":[dict(probability=q, category=panel["categories"][0]["label"], convention="ceiling") for q in (.5,.9)]},
            thresholds=[panel["categories"][0]["panel_value"]])
        validate_prepared_calibration(raw, mapping, cohort_id=cid, panel_id=binding["panel_id"])
        for kind in ("cohort", "panel_id", "geometry", "reference", "binding"):
            altered, data = copy.deepcopy(mapping), copy.deepcopy(raw)
            kwargs = dict(cohort_id=cid, panel_id=binding["panel_id"])
            if kind == "cohort": kwargs["cohort_id"] = "wrong"
            if kind == "panel_id": kwargs["panel_id"] = "wrong"
            if kind == "geometry": data["panel"]["categories"][0]["lower_closed"] = not data["panel"]["categories"][0]["lower_closed"]
            if kind == "reference": altered["reference_distribution"] = [1.] + [0.]*(len(panel["categories"])-1)
            if kind == "binding": altered["calibration_context"]["preparation_binding"]["unit_id"] = "changed"
            with pytest.raises(ValueError):
                validate_prepared_calibration(data, altered, **kwargs)


def test_public_prepare_then_batch(tmp_path):
    output = tmp_path/"prepared"
    assert main(["calibration-prepare",str(EXAMPLE/"counts.csv"),"--panels",str(EXAMPLE/"panels.csv"),
        "--roster",str(EXAMPLE/"roster.csv"),"--metadata",str(EXAMPLE/"metadata.json"),
        "--level",".75","--output-dir",str(output)]) == 0
    assert main(["batch",str(EXAMPLE/"future-summaries.csv"),"--panels",str(EXAMPLE/"panels.csv"),
        "--targets",str(output/"targets.csv"),"--calibrations",str(output/"calibrations.json"),
        "--output-dir",str(tmp_path/"batch")]) == 0
    records = json.loads((tmp_path/"batch"/"results.json").read_text())
    assert len(records) == 2 and all(r["status"] == "ok" for r in records)
    assert all("conformal_unavailable_reason" not in r["result"] for r in records)


def test_json_analysis_cannot_bypass_preparation_reference_binding(prepared):
    from mic_50_90 import analyse_spec
    mapping=copy.deepcopy(next(iter(prepared['calibrations'].values())))
    pid=mapping['calibration_context']['preparation_binding']['panel_id']
    panel=prepared['configuration']['panels'][pid]
    raw=dict(contract_version='1.0', mode='empirical', n=10, panel=panel,
        summaries={'quantiles':[dict(probability=q,category=panel['categories'][0]['label'],convention='ceiling') for q in (.5,.9)]},
        thresholds=[panel['categories'][0]['panel_value']], question_utility={'enabled':False}, **mapping)
    raw['reference_distribution']=[1.]+[0.]*(len(panel['categories'])-1)
    with pytest.raises(ValueError,match='reference'):
        analyse_spec(raw)


@pytest.mark.parametrize('field', ['wasserstein_calibration_manifest','calibration_context'])
def test_null_calibration_does_not_erase_returned_count(field):
    from test_count_updates import feature,specification,returned,calibration,sample_counts
    mapping=calibration()
    mapping[field]=None
    result=feature()(specification(),[returned()],calibration=mapping)
    assert sample_counts(result)==[(2,2),(1,2)]
    assert result['additional_information']['status']=='applied'
    assert 'conformal_unavailable_reason' in result


def test_public_csv_additional_count_resolves_decision_and_retains_orphan(tmp_path):
    from test_csv_workflows import inputs, write_csv
    inputs(tmp_path)
    row=dict(cohort_id="C",panel_id="P",variant_id="primary",n=10,mic50=2,mic90=16,rank_convention="ceiling",iid="true")
    write_csv(tmp_path/"summaries.csv",list(row),[row])
    target=dict(cohort_id="C",threshold=2,unit="mg/L",decision_operator="<",decision_fraction=".5")
    write_csv(tmp_path/"targets.csv",list(target),[target])
    answer=dict(cohort_id="C",threshold=2,unit="mg/L",count=3,n=10,source="source table")
    write_csv(tmp_path/"answers.csv",list(answer),[answer,{**answer,"cohort_id":"absent"}])
    assert main(["batch",str(tmp_path/"summaries.csv"),"--panels",str(tmp_path/"panels.csv"),
        "--targets",str(tmp_path/"targets.csv"),"--additional-counts",str(tmp_path/"answers.csv"),
        "--output-dir",str(tmp_path/"out"),"--fail-on-refusal"]) == 2
    records=json.loads((tmp_path/"out"/"results.json").read_text())
    assert records[0]["result"]["additional_information"]["status"] == "applied"
    assert records[0]["result"]["decision_results"][0]["sample"]["status"] == "supported"
    assert records[1]["status"] == "refused" and "Orphan" in records[1]["reason"]
    config=json.loads((tmp_path/"out"/"configuration.json").read_text())
    assert "additional_counts" in config["inputs"]
    assert config["cohorts"][0]["additional_counts"][0]["count"] == "3"
    report=(tmp_path/"out"/"report.html").read_text(encoding="utf-8")
    assert "Returned counts" in report and "source table" in report
    with (tmp_path/"out"/"results.csv").open(newline="",encoding="utf-8") as f:
        assert next(csv.DictReader(f))["additional_count_status"] == "applied"

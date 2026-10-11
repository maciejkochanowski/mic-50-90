import csv
import json

import pytest

from mic_50_90.cli import main


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def inputs(tmp_path):
    panel = []
    for i, level in enumerate([1,2,4,8,16]):
        panel.append(dict(panel_id="P", unit="mg/L", category=str(level),
                          lower="" if i == 0 else str(level/2), upper=str(level),
                          lower_closed="false", upper_closed="true", panel_value=level))
    write_csv(tmp_path/"panels.csv", list(panel[0]), panel)
    targets = [dict(cohort_id="C", threshold=t, unit="mg/L") for t in (2,3,8)]
    write_csv(tmp_path/"targets.csv", list(targets[0]), targets)
    return tmp_path


def run(tmp_path, command, filename):
    return main([command, str(tmp_path/filename), "--panels", str(tmp_path/"panels.csv"),
                 "--targets", str(tmp_path/"targets.csv"), "--output-dir", str(tmp_path/"out")])


def test_batch_union_missing_panel_and_all_three_report_layers(tmp_path):
    inputs(tmp_path)
    row = dict(cohort_id="C", panel_id="P", variant_id="primary", n=10,
               mic50="2", mic90="16", rank_convention="ceiling", rank50="", rank90="",
               minimum="", maximum="", iid="true", confidence_level=.95)
    rows = [row, {**row,"variant_id":"other","rank_convention":"explicit",
                  "rank50":4,"rank90":8}, {**row,"cohort_id":"bad","panel_id":"missing"}]
    write_csv(tmp_path/"summaries.csv", list(row), rows)
    write_csv(tmp_path/"targets.csv", ["cohort_id","threshold","unit"],
              [dict(cohort_id=c,threshold=2,unit="mg/L") for c in ("C","bad")])
    assert run(tmp_path,"batch","summaries.csv") == 0
    results = json.loads((tmp_path/"out"/"results.json").read_text())
    assert results[0]["status"] == "ok"
    bound = results[0]["result"]["reporting_uncertainty_envelope"]["envelope"][0]
    assert bound["panel_recorded_estimand"]["upper"]["count"] == 6
    assert results[1]["status"] == "refused"
    assert "panel" in results[1]["reason"].lower()
    report = (tmp_path/"out"/"report.html").read_text(encoding="utf-8")
    for term in ("60.00%", "6/10", "Finite sample", "iid population", "New cohort",
                 "reference", "missing"):
        assert term in report
    assert (tmp_path/"out"/"configuration.json").exists()
    assert (tmp_path/"out"/"results.csv").exists()


def test_reporting_audit_preserves_censored_uncertainty_and_observed_gain(tmp_path):
    inputs(tmp_path)
    rows = [dict(cohort_id="C",panel_id="P", category=str(t),count=c,
                 rank_convention="ceiling",iid="false",confidence_level=.95)
            for t,c in zip([1,2,4,8,16],[1,4,2,1,2])]
    write_csv(tmp_path/"counts.csv",list(rows[0]),rows)
    assert run(tmp_path,"reporting-audit","counts.csv") == 0
    record = json.loads((tmp_path/"out"/"results.json").read_text())[0]
    audit = record["reporting_audit"]
    middle = next(x for x in audit["full_histogram"] if x["threshold"]==3)
    assert middle["recorded"] == pytest.approx(.5)
    assert middle["latent_lower"] == pytest.approx(.3)
    assert middle["latent_upper"] == pytest.approx(.5)
    assert audit["observed_gain"] >= audit["guaranteed_gain"] - 1e-10
    assert audit["all_target_counts_width"] == pytest.approx(0)
    assert "does not identify" in (tmp_path/"out"/"report.html").read_text()


def test_missing_rank_is_refused_not_guessed(tmp_path):
    inputs(tmp_path)
    row=dict(cohort_id="C",panel_id="P",variant_id="primary",n=10,mic50=2,mic90=16,
             rank_convention="",iid="false")
    write_csv(tmp_path/"summaries.csv",list(row),[row])
    assert run(tmp_path,"batch","summaries.csv")==0
    r=json.loads((tmp_path/"out"/"results.json").read_text())[0]
    assert r["status"]=="refused"
    assert "rank_convention" in r["reason"]


def test_duplicate_category_and_orphan_target_are_not_silent(tmp_path):
    inputs(tmp_path)
    row=dict(cohort_id="C",panel_id="P",category="1",count=10,rank_convention="ceiling")
    write_csv(tmp_path/"counts.csv",list(row),[row,row])
    assert run(tmp_path,"reporting-audit","counts.csv")==0
    r=json.loads((tmp_path/"out"/"results.json").read_text())[0]
    assert r["status"]=="refused"
    assert "duplicate" in r["reason"].lower()

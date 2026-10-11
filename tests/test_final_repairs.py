import argparse
import json

import pytest

from mic_50_90.cli import build_parser
from mic_50_90.model import MICPanel


def test_every_command_option_has_help_text():
    root = build_parser()
    missing = []
    for action in root._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, parser in action.choices.items():
                missing += [(name, a.option_strings[0]) for a in parser._actions
                            if a.option_strings and not a.help and "--help" not in a.option_strings]
    assert not missing


@pytest.mark.parametrize("panel, message", [([1, 2], "panel must be an object"),
                                            ({"categories": ["a", "b"]}, "must be an object with a label"),
                                            ({"categories": [{"upper": 1}]}, "must be an object with a label")])
def test_malformed_panel_is_refused_with_a_message(panel, message):
    with pytest.raises(ValueError, match=message):
        MICPanel.from_dict(panel)


def test_non_finite_planning_limit_still_writes_results(tmp_path):
    from mic_50_90.cli import main
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"cohort_id": "c", "unit": "mg/L", "n": 20, "panel": {"levels": [1, 2, 4]},
                                  "summaries": {"quantiles": [{"probability": .5, "category": "2"}]}}), encoding="utf-8")
    main(["distribution", str(source), "--population-planning-time-limit", "inf", "--output-dir", str(tmp_path / "out")])
    configuration = json.loads((tmp_path / "out/configuration.json").read_text(encoding="utf-8"))
    assert configuration["population_planning_time_limit"] == "inf"
    assert (tmp_path / "out/results.json").is_file()

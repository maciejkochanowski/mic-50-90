from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from mic_50_90.analysis import analyse_spec


def test_examples_validate_against_v5_input_and_output_schemas():
    input_schema = json.loads(Path("schemas/input.schema.json").read_text())
    output_schema = json.loads(Path("schemas/output.schema.json").read_text())
    for path in (Path("examples/empirical.json"), Path("examples/population.json")):
        raw = json.loads(path.read_text())
        Draft202012Validator(input_schema).validate(raw)
        Draft202012Validator(output_schema).validate(analyse_spec(raw))

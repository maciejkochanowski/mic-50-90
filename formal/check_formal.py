"""Compile P6Core.lean, audit its axiom dependencies and run the five negative controls.

Run from this directory after `lake update` and `lake exe cache get Mathlib.Tactic Mathlib.Data.Real.Basic`:

    python check_formal.py --receipt RECEIPT.json

The check passes when P6Core.lean compiles, prints the axiom dependencies of all its theorems and
uses no axioms beyond propext, Classical.choice and Quot.sound, and when every control is rejected:
Lean rejects the three false arguments, and the axiom audit rejects the placeholder proof (sorry) and
the added axiom, which Lean itself accepts. Each control is a copy of P6Core.lean with one addition
before its last line; the copies are deleted afterwards.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'P6Core.lean'
ALLOWED = {'propext', 'Classical.choice', 'Quot.sound'}
END = 'end MIC5090'

CONTROLS = {
    'false_concavity_of_example': ('lean', '''
theorem control_example_concave :
    ∀ i, i+2 ≤ 4 → NonconcaveExample (i+2)-NonconcaveExample (i+1) ≤
      NonconcaveExample (i+1)-NonconcaveExample i := by
  intro i hi
  have hi2 : i ≤ 2 := by omega
  interval_cases i <;> norm_num [NonconcaveExample]
'''),
    'false_count_row': ('lean', '''
theorem control_count_row_off_by_one {I : Type*} (D : I → I → ℤ)
    (diagonal : ∀ a, D a a = 0) (z a b : I) :
    (D a b-D a z) - (D a a-D a z) = D a b + 1 := by
  rw [diagonal]
  omega
'''),
    'false_endpoint_order': ('lean', '''
theorem control_endpoint_order_without_concavity (n : ℕ) (U : ℕ → ℝ) (d : ℕ) :
    Lower n U d ≤ U d := by
  unfold Lower
  linarith
'''),
    'placeholder': ('audit', '''
theorem control_placeholder : (2:ℝ) ≤ 1 := by
  sorry

#print axioms control_placeholder
'''),
    'extra_axiom': ('audit', '''
axiom control_extra_axiom : (2:ℝ) ≤ 1

theorem control_uses_extra_axiom : (2:ℝ) ≤ 1 := control_extra_axiom

#print axioms control_uses_extra_axiom
'''),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_lean(path):
    start = time.monotonic()
    r = subprocess.run(['lake', 'env', 'lean', path.name], cwd=HERE, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr, time.monotonic() - start


def axiom_reports(output):
    reports = {name: [a.strip() for a in found.split(',') if a.strip()]
               for name, found in re.findall(r"'MIC5090\.(\w+)' depends on axioms: \[([^\]]*)\]", output)}
    reports.update({name: [] for name in re.findall(r"'MIC5090\.(\w+)' does not depend on any axioms", output)})
    return reports


def error_lines(output, name):
    return [int(n) for n in re.findall(re.escape(name) + r':(\d+):\d+: error', output)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    text = SOURCE.read_text(encoding='utf-8')
    lines = text.rstrip('\n').split('\n')
    if lines[-1] != END:
        raise SystemExit('P6Core.lean must end with ' + END)
    theorems = re.findall(r'^theorem (\w+)', text, flags=re.M)
    version = subprocess.run(['lake', 'env', 'lean', '--version'], cwd=HERE, capture_output=True, text=True).stdout.strip()

    code, output, seconds = compile_lean(SOURCE)
    reports = axiom_reports(output)
    main_check = dict(exit_code=code, seconds=round(seconds, 1), theorems=len(theorems),
                      theorems_reported=sum(t in reports for t in theorems),
                      theorems_with_allowed_axioms_only=sum(t in reports and set(reports[t]) <= ALLOWED for t in theorems),
                      uses_sorry='sorryAx' in output or "declaration uses 'sorry'" in output, axioms=reports)
    main_check['passed'] = (code == 0 and main_check['theorems_with_allowed_axioms_only'] == len(theorems)
                            and not main_check['uses_sorry'])

    controls = {}
    for name, (kind, addition) in CONTROLS.items():
        path = HERE / f'_control_{name}.lean'
        path.write_text('\n'.join(lines[:-1]) + '\n' + addition + '\n' + END + '\n', encoding='utf-8')
        try:
            code_c, output_c, seconds_c = compile_lean(path)
        finally:
            path.unlink()
        errors = error_lines(output_c, path.name)
        added = axiom_reports(output_c)
        offending = {t: a for t, a in added.items() if t.startswith('control_') and not set(a) <= ALLOWED}
        if kind == 'lean':
            rejected = code_c != 0 and bool(errors) and min(errors) >= len(lines)
            reason = next((m for m in output_c.splitlines() if ': error' in m), '')
        else:
            rejected = code_c == 0 and bool(offending)
            reason = json.dumps(offending)
        controls[name] = dict(rejected_by='Lean' if kind == 'lean' else 'axiom audit', exit_code=code_c,
                              seconds=round(seconds_c, 1), rejected=rejected,
                              reason=reason.replace(str(HERE) + '/', ''))

    receipt = dict(lean=version, source='P6Core.lean', source_sha256=sha(SOURCE), allowed_axioms=sorted(ALLOWED),
                   compilation=main_check, controls=controls,
                   passed=main_check['passed'] and all(c['rejected'] for c in controls.values()))
    args.receipt.write_text(json.dumps(receipt, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=receipt['passed'], theorems=len(theorems),
                          controls={k: v['rejected'] for k, v in controls.items()})))
    sys.exit(0 if receipt['passed'] else 1)


if __name__ == '__main__':
    main()

#!/bin/bash
# Mutation testing of the thirteen critical functions (evaluation/README.md, "Tests, coverage and mutations").
# Submit from the repository root: sbatch evaluation/mutation.sbatch
#SBATCH --job-name=mic-50-90-mutation
#SBATCH --account=plgsoa27eupahw-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=96
#SBATCH --mem-per-cpu=2G
#SBATCH --time=24:00:00
#SBATCH --output=mutation-%j.log

set -euo pipefail
module load Python/3.11.5
VENV=${VENV:-$SCRATCH/venv-mic-50-90-mutation}
PYTHON="$VENV/bin/python"
cd "${SLURM_SUBMIT_DIR:-.}"
if ! test -x "$PYTHON"; then
  python3 -m venv "$VENV"
  "$PYTHON" -m pip install --quiet --upgrade pip
  "$PYTHON" -m pip install --quiet -e ".[test]" mutmut==3.8.0 "pytest<9" nodejs-wheel
fi
export PATH="$VENV/bin:$PATH" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# tests that start a separate Python process must import the mutated package
SITE=$("$PYTHON" -c "import site; print(site.getsitepackages()[0])")
echo "$PWD/mutants/src" > "$SITE/000-mutants.pth"
trap 'rm -f "$SITE/000-mutants.pth"' EXIT
FUNCTIONS=(
  "mic_50_90.range_certificates.x_binomial_shape_certificate__mutmut_*"
  "mic_50_90.range_certificates.x_split_count_cell__mutmut_*"
  "mic_50_90.decisions.x_classify_intervals__mutmut_*"
  "mic_50_90.utility.x__prefix_distances__mutmut_*"
  "mic_50_90.validation.x_ceiling_rank__mutmut_*"
  "mic_50_90.count_updates.x_counts_from_percentage__mutmut_*"
  "mic_50_90.joint_population.x__cp_outer__mutmut_*"
  "mic_50_90.range_population.x_critical_score__mutmut_*"
  "mic_50_90.exact_population.x__bonferroni_level__mutmut_*"
  "mic_50_90.sufficient_reporting.x_verify_reporting__mutmut_*"
  "mic_50_90.sufficient_reporting.x_plan_reporting__mutmut_*"
  "mic_50_90.conformal.x_conformal_rank__mutmut_*"
  "mic_50_90.dro.x_critical_radius__mutmut_*"
)
"$VENV/bin/mutmut" run --max-children "${SLURM_CPUS_PER_TASK:-96}" "${FUNCTIONS[@]}" || true
"$VENV/bin/mutmut" results --all true > mutation-results.txt || true
tail -5 mutation-results.txt

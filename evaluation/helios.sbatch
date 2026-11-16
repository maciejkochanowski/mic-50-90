#!/bin/bash
# Run every comparison of the evaluation on one 192-core Helios node.
#
# Submit from the repository root:
#   sbatch evaluation/helios.sbatch
# On the first run the job creates the Python environment in $VENV (default $HOME/venv-mic-50-90)
# on the compute node, because the Python module is built for the compute nodes' operating system.
#
# The comparisons run one after another, so that the timed population comparison has the whole
# node. Each script skips finished work, so a resubmitted job continues where it stopped.

#SBATCH --job-name=mic-50-90-evaluation
#SBATCH --account=plgsoa27eupahw-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=128G
#SBATCH --time=01:00:00
#SBATCH --output=evaluation-%j.log

set -euo pipefail
module load Python/3.11.5
VENV=${VENV:-$HOME/venv-mic-50-90}
PYTHON="$VENV/bin/python"
WORKERS=${SLURM_CPUS_PER_TASK:-192}
OUTPUT=${OUTPUT:-evaluation/results}
cd "${SLURM_SUBMIT_DIR:-.}"
if ! test -x "$PYTHON"; then
  python3 -m venv "$VENV"
  "$PYTHON" -m pip install --quiet --upgrade pip
  "$PYTHON" -m pip install --quiet -e . pba==0.90.4
fi
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

"$PYTHON" -c "import mic_50_90, platform; print('mic-50-90', mic_50_90.__version__, platform.node())"
"$PYTHON" evaluation/population_comparison.py --output "$OUTPUT" --workers "$WORKERS" --budget 120
"$PYTHON" evaluation/coverage_simulation.py --output "$OUTPUT" --workers "$WORKERS" --replicates 5000
"$PYTHON" evaluation/complete_tables.py --output "$OUTPUT" --workers "$WORKERS"
"$PYTHON" evaluation/controlled_reports.py --output "$OUTPUT" --workers "$WORKERS"
"$PYTHON" evaluation/sufficient_reporting.py --output "$OUTPUT"
"$PYTHON" evaluation/calibration.py --output "$OUTPUT" --workers "$WORKERS"
"$PYTHON" evaluation/pba_comparison.py --output "$OUTPUT"
"$PYTHON" evaluation/reporting_controls.py --output "$OUTPUT"
"$PYTHON" evaluation/planning_controls.py --output "$OUTPUT"
"$PYTHON" evaluation/count_extrema_controls.py --output "$OUTPUT"
"$PYTHON" evaluation/population_controls.py --output "$OUTPUT"
"$PYTHON" evaluation/endpoint_selection.py --output "$OUTPUT"
"$PYTHON" evaluation/examples_check.py --output "$OUTPUT"
"$PYTHON" evaluation/summarize.py --output "$OUTPUT"

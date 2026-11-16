#!/bin/bash
# Run the confirmation evaluation (PROTOCOL.md) on Helios.
#
# Submit from the repository root, after download_sources.py has filled evaluation/sources. The work
# can be split into shards that run at the same time; a final job without SHARD collects them:
#   sbatch -c 48 --export=ALL,PART=coverage,SHARD=0/8 evaluation/helios_confirmation.sbatch   (... 7/8)
#   sbatch -c 4  --export=ALL,PART=coverage evaluation/helios_confirmation.sbatch               (collect)
# PART is one of: prepare, population, coverage, synthetic, calibration-real, calibration-synthetic,
# summary. Without SHARD a part runs (or completes) all of its work. Finished work is never repeated.

#SBATCH --job-name=mic-50-90-confirmation
#SBATCH --account=plgsoa27eupahw-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem-per-cpu=2G
#SBATCH --time=12:00:00
#SBATCH --output=confirmation-%x-%j.log

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
  "$PYTHON" -m pip install --quiet -e ".[benchmark]" pba==0.90.4
fi
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
SHARDING=()
if test -n "${SHARD:-}"; then SHARDING=(--shard "$SHARD"); fi

"$PYTHON" -c "import mic_50_90, platform; print('mic-50-90', mic_50_90.__version__, platform.node())"
case "${PART:?set PART}" in
  prepare)
    before=$(for f in evaluation/data/benchmark/*.gz; do zcat "$f" | sha256sum; done)
    "$PYTHON" evaluation/prepare_benchmark.py
    after=$(for f in evaluation/data/benchmark/*.gz; do zcat "$f" | sha256sum; done)
    test "$before" = "$after" && echo "benchmark tables rebuilt with identical content" || { echo "benchmark tables differ"; exit 1; } ;;
  population)
    "$PYTHON" evaluation/confirmation_population.py --output "$OUTPUT" --workers "$WORKERS" "${SHARDING[@]}" ;;
  coverage)
    "$PYTHON" evaluation/confirmation_coverage.py --output "$OUTPUT" --workers "$WORKERS" "${SHARDING[@]}" ;;
  synthetic)
    "$PYTHON" evaluation/synthetic_coverage.py --output "$OUTPUT" --workers "$WORKERS" "${SHARDING[@]}" ;;
  calibration-real)
    "$PYTHON" evaluation/external_calibration.py --output "$OUTPUT" --workers "$WORKERS" --parts real "${SHARDING[@]}" ;;
  calibration-synthetic)
    "$PYTHON" evaluation/external_calibration.py --output "$OUTPUT" --workers "$WORKERS" --parts synthetic "${SHARDING[@]}" ;;
  summary)
    "$PYTHON" evaluation/external_calibration.py --output "$OUTPUT" --workers "$WORKERS"
    "$PYTHON" evaluation/summarize.py --output "$OUTPUT" ;;
esac

#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=7
#SBATCH --gpus-per-node=1
#SBATCH --mem=30G
#SBATCH --time=00:15:00
#SBATCH --job-name=dnabert-base-prior
set -euo pipefail
R=${DNABERT2_RUN_DIR:-/path/to/dnabert2-prior}
srun bash "$R/runtime.sh" "$R/evaluate.py" --root "$R" --stage pilot
srun bash "$R/runtime.sh" "$R/evaluate.py" --root "$R" --stage evaluate

#!/bin/bash
#SBATCH --account=project_465003339
#SBATCH --partition=dev-g
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=7
#SBATCH --gpus-per-node=1
#SBATCH --mem=30G
#SBATCH --time=00:15:00
#SBATCH --job-name=dnabert-base-prior
#SBATCH --output=/scratch/project_465003339/ajeppese/bend-dnabert2-prior-20261027/logs/%j.out
set -euo pipefail
R=/scratch/project_465003339/ajeppese/bend-dnabert2-prior-20261027
srun bash "$R/runtime.sh" "$R/evaluate.py" --root "$R" --stage pilot
srun bash "$R/runtime.sh" "$R/evaluate.py" --root "$R" --stage evaluate

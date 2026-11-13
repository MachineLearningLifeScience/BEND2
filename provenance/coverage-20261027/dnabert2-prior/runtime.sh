#!/bin/bash
set -euo pipefail
R=${DNABERT2_RUN_DIR:-/path/to/dnabert2-prior}
O=${DNABERT2_RUNTIME_DIR:-/path/to/runtime}
S=${DNABERT2_MODEL_CACHE_DIR:-/path/to/model-cache}
I=${DNABERT2_CONTAINER:-/path/to/pytorch-rocm-6.2.4-python-3.12-pytorch-v2.7.1.sif}
T=/tmp/dnabert-prior-${UID}-${SLURM_JOB_ID:-login}
mkdir -p "$T/miopen" "$R/cache/${SLURM_JOB_ID:-login}"
V=${ROCR_VISIBLE_DEVICES:-0}
unset SINGULARITY_BIND SINGULARITY_BINDPATH APPTAINER_BIND APPTAINER_BINDPATH
exec singularity exec --cleanenv --bind "$R:$R" --bind "$O:$O:ro" --bind "$S:$S:ro" --bind "$T:$T" \
 --bind "$O/environment/python-packages.squashfs:/opt/packages:image-src=/" \
 --env "DNABERT2_RUN_DIR=$R" --env "DNABERT2_MODEL_DIR=${DNABERT2_MODEL_DIR:-$S/extra-models-direct/models--zhihan1996--DNABERT-2-117M/snapshots/b5d88cda421f106afef78cd286200a5b5b8f6fea}" \
 --env "PYTHONPATH=$S/statistics-packages:/opt/packages" --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
 --env "HF_MODULES_CACHE=$R/cache/${SLURM_JOB_ID:-login}" --env "XDG_CACHE_HOME=$T" \
 --env "MIOPEN_USER_DB_PATH=$T/miopen" --env "TRITON_CACHE_DIR=$T/triton" \
 --env OMP_NUM_THREADS=6 --env OPENBLAS_NUM_THREADS=1 --env MKL_NUM_THREADS=1 \
 --env PYTHONDONTWRITEBYTECODE=1 --env "ROCR_VISIBLE_DEVICES=$V" "$I" python -u "$@"

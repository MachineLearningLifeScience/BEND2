# Evo2 extraction review — 2 November 2026

**Recommendation: accept the extraction as completion of the native-FP8 Evo2 20B run, with the two-GPU adaptation disclosed.** The previous BF16 rejection does not apply to this return. No extraction defect requiring another full run was found. This conclusion rests on source review, matching provenance, reported runtime controls, and independently checked arrays; GPU inference was not independently rerun here. The separate CPU evaluation audit must also pass before integrating the result.

The reference is the stopped 23 September handoff in `output/evo2-collaborator-handoff-stopped-20260923/evo2-gtex-handoff`. The returned package is `evo2-results` alongside this report. No returned Python code or pickle was executed. Arrays were read with `allow_pickle=False`; the state archive was inspected using ZIP metadata and static pickle opcodes only.

## Independently verified

- All 25 returned manifest entries have matching sizes and SHA256 hashes. The feature hash also matches extraction `COMPLETE.json`.
- The matrix is float16, shape 19,282 × 512; every row is finite and nonzero. The boolean completion mask is entirely true.
- All **4,489 originally completed rows are exactly equal** to the original FP8 snapshot. All 14,793 formerly incomplete rows are populated. The original completed indices are the contiguous prefix 0–4,488.
- Recorded hashes match the original snapshot's embeddings, completion mask and resume state; prepared protocol; dense extraction helper; projection helper; vendor-source manifest; and entire source-packet manifest. The returned runner and adapter match their recorded hashes. The checkpoint and sequence hashes remain the original pinned values, with active hash checks in the runner; the large checkpoint was not independently available here.
- Static inspection of the final state archive finds the same 21 TE module names, one CPU RNG state, two CUDA RNG states, and a 19,282-element all-true mask matching `completed.npy`. The original state has one CUDA RNG state and a matching 4,489-completed mask. This is a structural check, not GPU deserialization or numerical state replay.

## FP8 and the two-GPU adaptation

The returned `run_evo2_local.py` is a narrow diff of the original `run_evo2.py`. It permits exactly two Hopper GPUs through an explicit flag, records their environment, installs `multi_gpu_state.py`, clears each device's cache, and extends the original one-device RNG list. It does not disable FP8, change weights, reorder genes, shorten context, change pooling/projection, or alter numerical thresholds.

The frozen Evo2 configuration enables FP8 input projections. Its `TELinear.forward` executes Transformer Engine FP8 autocast. Two visible GPUs invoke the existing Vortex block placement: blocks 0–11 on GPU 0 and 12–23 on GPU 1. This distributes model blocks while keeping a single serial gene stream; it is not independent gene-shard extraction. The unchanged hook captures `blocks.20.mlp.l3`, and the original unused-tail offload remains safe because extraction exits before blocks 21–23.

The adapter sets the CUDA context for state capture/restoration. If scale/history tensors occupy the wrong device, it removes the old recipe state and associated quantizers, then delegates to TE's original loader to rebuild them and copy the serialized values. It checks their final placement. This matches [TE 2.18's state implementation](https://raw.githubusercontent.com/NVIDIA/TransformerEngine/v2.18/transformer_engine/pytorch/module/base.py): rebuilding can inherit old tensor objects, while loading copies saved scales/history and synchronizes the current device. No deliberate scale reset or BF16 substitution is present.

The source device's RNG is preserved, and the added device receives its existing seeded state. Evaluation/inference mode remains enabled. Subsequent two-device checkpoints preserve both RNG states; the exact-replay gate remains mandatory.

## Runtime controls

The three short and three full-window reference comparisons, relative-L2 threshold **0.005**, exact repeated extraction, and comparison against cached gene 0 are unchanged (`run_evo2_local.py:271–338`). Production state is restored after the test calls, before serial continuation.

`LOCAL_ADAPTATION.json` reports all six errors and the resume-control error as **0.0**, exact replay true, first at 4,489 completed genes and then after a two-gene smoke continuation. `RESUME_VALIDATION.json` records the second pass at **4,491** completed genes, with PID 994437 matching the final runtime environment and progress record. The environment reports two NVIDIA H100 80GB GPUs, CUDA 13.0, TE 2.18.0, and no differences from the pinned package versions. These are returned execution records, not independently rerun GPU measurements.

`progress.json` stops at 19,281 because it is periodic. The subsequent complete mask, final checkpoint mask, feature hash and `COMPLETE.json` consistently establish 19,282; this is not an incomplete run.

## Remaining provenance gaps

The package omits the Slurm wrappers, raw scheduler/stdout logs, and `test_multi_gpu_state.py` whose hashes appear in the adaptation record. It also omits the first validation process's standalone environment/report and the two-gene smoke checkpoint. The embedded initial report and final restart report provide a coherent history but do not independently reproduce every intermediate step.

The runner loads `controls/reference.npz` without recording its hash, and the return includes numerical error summaries rather than the six freshly computed control vectors. The original reference hash is `23b2209b3aa98f48993c8ad54e90f266db6db8375662970f05f7afb6483d2535`. Archiving the executed control file or its hash, together with the missing logs/test source, would make the record stronger. These omissions limit independent runtime reconstruction; they do not supply evidence that the unchanged gates were bypassed or that FP8 was disabled.

The previously documented eight held-out X/Y pseudoautosomal sequence duplicates are inherited from the common benchmark split. They remain a separate shared-cohort sensitivity issue, not a new extraction defect or a reason to change Evo2's split alone. No manuscript, website, split, remote or GPU job was changed by this audit.

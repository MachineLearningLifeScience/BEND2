# DNABERT2 hidden-base query: diagnostic, not a leaderboard score

**Decision:** leave the comparable hidden-base score unavailable for this interface. The experiment below evaluates a deliberately specified singleton-token query. It does not establish that DNABERT2 lacks sequence knowledge.

## What was tested

The frozen 512-window prior panel contains one 1,200-bp sequence per genomic block. Base 600 (zero-based) was removed **before** tokenization. The 600 left and 599 right visible bases were independently BPE-tokenized, with one MASK between them and the model's native CLS/SEP pair around the full query. All 1,199 visible bases were preserved; inputs contained 210–276 tokens, without truncation. Substituting the missing base with each of A/C/G/T left every query unchanged.

The official pretrained masked-language-model checkpoint was used in FP32 with its original eager attention. No weights were fitted, no calibration was applied, and no query settings were selected using results. MASK logits were restricted to the four singleton nucleotide IDs (5–8) and renormalized. This is a **fixed-boundary single-base query**, not DNABERT2's native whole-token masking task. We also retained the original probability mass assigned to those four tokens.

## Result and interpretation

The query yielded **6.203 bits** per hidden base (95% genomic-block bootstrap interval 5.795–6.604) and **24.80% accuracy** (21.29–28.52%). Intervals use the benchmark's 4,000 bootstrap draws and seed 20260910. These are diagnostic results, not accepted leaderboard entries.

Under ordinary DNABERT2 tokenization, **none of the 512 target bases is a singleton token**: their native tokens span 2–17 bases. Singleton tokens account for only 279 of 118,874 tokens (0.235%) across these windows. The artificial query therefore forces a token format rarely encountered in ordinary tokenization. The four singleton outputs together receive a median probability mass of only **0.000002964** before renormalization. Their conditional probabilities are strongly biased: mean A/C/G/T probabilities are 0.359/0.547/0.059/0.034; argmax calls are A=191, C=289, G=25 and T=7.

The computation defines a normalized distribution over bases, but the tiny retained mass and mismatch with native tokenization make it unsuitable as an unqualified comparison with the established base-level interfaces. A suitable nucleotide probability interface for DNABERT2 remains an open evaluation-method question. We did not search for a better query using these labels.

## Validation and files

All pretrained MLM weights loaded, with no missing, unexpected or mismatched keys. Batched versus individual log probabilities agreed within 0.0000262. The original padded-width comparison included the longest query and was therefore redundant; a separate check compared widths 235 and 276 without altering predictions. It passed, with a maximum log-probability difference of 0.0000169 (`padding-audit.json`, job `23219824`).

- `PROTOCOL.json`: fixed query definition, checkpoint revision, source and input hashes.
- `RESULT.json`: exact metrics, intervals, runtime and weight-loading checks.
- `diagnostic-per-window.csv`: genomic block, target, four conditional probabilities, full-vocabulary mass, loss and prediction.
- `tokenization-audit.json`: native token lengths and conditional-query confusion counts.
- `evaluate.py`, `check_padding.py`, `tokenization_audit.py`: executable sources; `SHA256SUMS.json` records artifact hashes.

Checkpoint: `zhihan1996/DNABERT-2-117M`, revision `b5d88cda421f106afef78cd286200a5b5b8f6fea`; official weights SHA-256 `75c91dc7bd0eea50f63e2ce6aeac2d9f20980f9efc9c715a26e4efa1e369de1c` (independently matched to the pinned Hugging Face LFS object). LUMI evaluation job: `23219642`, completed in 66 seconds. No benchmark-table or manuscript files were changed.

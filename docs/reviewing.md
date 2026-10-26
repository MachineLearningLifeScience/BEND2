# Review a leaderboard submission

Anyone can propose a result. Maintainers review the setup and independently
rescore **every submitted task** before accepting it. Accepted results carry
the label **Contributor evaluated**. Independent model reruns are selective;
only tasks actually rerun can carry **Reproduced by BEND**.

Regular package use requires none of this. Local evaluation, notebooks, saved
tables and model comparisons work without GitHub or publication declarations.
Reviewer and site-build commands are grouped under `bend2 admin`; use
`bend2 admin --help` to list them.

## Rescore the evidence

Use an installed, trusted version of BEND from the publication branch. Do not
install the contributor's PR as the reviewer tool. Download the linked evidence
ZIP and the contribution JSON, then run:

```bash
bend2 admin rescore-submission submissions/community-IDENTITY.json \
  --bundle /path/to/downloaded/submission.zip \
  --output reviews/community-IDENTITY.json \
  --cache-dir /path/to/benchmark-cache
```

This reads the ZIP as data. It never imports its adapter or executes its code.
The command checks archive hashes and protocols, then loads the installed
benchmark's pinned labels and cohorts. It reconstructs:

| Task | Independently checked from prediction evidence |
| --- | --- |
| Sequence prior | All 512 windows, hidden bases, query probabilities, within-window loss, accuracy and block bootstrap |
| OpenSplice and context | Complete record IDs, trusted targets, group/fold membership, group correlations and macro bootstrap |
| Background | Both trusted state means, paired contrasts, fold membership, group correlations and bootstrap |
| Repair | Frozen requests and candidate menus, direct-swap targets, nominated edits, measured percentile ranks and element bootstrap |
| Cell-selective design | Full candidate menus, no-edit and tied decisions, trusted measured outcomes, nested aggregation and locus bootstrap |
| Atlas | All candidate IDs, 16 requests, 10 choices per request, intended comparison cohorts and both measured replicate gains |
| Tissue identification | Common test genes, trusted expression profiles, tissue retrieval and all 10,000 whole-gene bootstrap draws |

Every submitted task must pass before a receipt is written. Missing records,
duplicates, altered labels, incorrect selections or mismatched scores fail the
review. Undefined groups are handled by the frozen scientific protocol.
Same-prediction metric comparison uses an absolute tolerance of `1e-10` in the
original task units; this does not affect ranking or selection decisions.

No model weights or GPU are needed. The first intervention review may download
the pinned source datasets; subsequent reviews reuse the cache. GTEx rescoring
uses its bundled labels and gene IDs, without downloading the genome or requiring
`py2bit`. Its exact bootstrap can take several minutes on a CPU.

The receipt binds the complete contribution content and evidence archive hashes,
the scorer source fingerprints, checked scopes, recomputed metrics and time.
Changing a model declaration, score, coverage or evidence URL/hash makes it stale.
Use a new output path when rescoring a correction, review the replacement, then
replace the old receipt. This prevents accidentally erasing reproduction history.

`bend2 admin validate-submission --bundle ...` remains a faster integrity check. It does
not perform trusted rescoring. A passing receipt also cannot establish which
weights ran, how embeddings/readouts were fitted, or absence of label leakage.
Validation-loss grids are checked for internal consistency, not independently
refitted from predictions.

## Review and accept

Review the pinned checkpoint, adapter, representation, pooling, full input
handling, fitting procedure and training-data disclosure. Check that a model
does not silently crop a task's required input. Resolve material discrepancies
in the PR before publication. No new form is needed from contributors: these
are the existing model declarations, adapter and generated evidence.

Generate the receipt yourself with trusted code. Add it under `reviews/` with
the same filename as the contribution, then review and merge both. Receipt JSON
is not a digital signature: anyone can write a file with those fields. Authority
comes from maintainer review on the protected publication branch.

Before public launch, configure the publication branch to require maintainer
and code-owner review, dismiss approvals after changes, and require CI. The
included `CODEOWNERS` identifies the repository owner for submissions, review
records and reviewer code; it does not enable those repository settings. Deploy
only from the publication branch after merge. Do not run contributed adapters
in privileged CI or on a cluster login node.

The normal website build requires a matching receipt for every community record.
It reads saved receipts and does not repeat downloads or rescoring. For a local
PR preview only:

```bash
BEND2_PREVIEW_SUBMISSIONS=1 npm --prefix website run build
```

PR CI sets that flag so a valid new submission can be inspected before the
maintainer adds a receipt. Preview mode deliberately labels every community row
and task **Awaiting review**, even if the PR includes a proposed review receipt.
A preview cannot grant an official reproduction label.
Push builds use the strict publication path. A stale or malformed receipt fails
both modes. Neither build mode changes the frozen paper rows or score anchors.

## Independently reproduce selected tasks

Use independent reruns for launch reference examples, leading or surprising
results, unresolved setup questions and a random sample of other contributions.
Select tasks based on the scientific question and available compute. Most
contributors can publish after rescoring and setup review without waiting for
our GPU queue. If a material discrepancy appears, withhold or withdraw the
affected entry until resolved; preserve the correction history in its PR.

After inspecting the adapter and dependencies, run it in an isolated job on
Lumi or another suitable machine. Use a new result directory and a **fresh
inference cache**. A verified source-data mirror can be shared; do not reuse the
contributor's embedding or probability cache. Rerunning only the scorer does
not qualify. Keep the same immutable weights and declared interface/configuration.

Export the independent run with `bend2 export`, host its ZIP, then record exactly
the tasks you reran:

```bash
bend2 admin record-reproduction submissions/community-IDENTITY.json \
  --review reviews/community-IDENTITY.json \
  --run results/independent-rerun --tasks atlas_profile \
  --evidence-url https://example.org/independent-rerun.zip \
  --reviewer YOUR_GITHUB_HANDLE \
  --notes "Independent job; pinned weights; fresh inference cache; hardware and setup details" \
  --attest-independent
```

This verifies the model/interface identity, rejects reuse of the submitted run,
independently rescores the rerun evidence, and compares the selected metrics
and intervals. The fixed absolute agreement tolerance is `1e-4` in each metric's
original units (percentage points for percentage metrics); Atlas additionally
checks both replicate gains. It is a small numerical tolerance, not permission
to select a better run. A larger discrepancy needs investigation, not a wider
tolerance chosen afterwards. The public score remains the contributor's score;
the rerun estimate and evidence are linked in that task's details.

The explicit attestation records a human responsibility: result files cannot
prove that an independent execution occurred. A copied run with edited metadata
could still deceive software checks. Maintainers must review the job provenance.
Neither rescoring nor a model rerun proves the absence of benchmark contamination.

The same operations are available from `bend2.reviews.rescore_submission`,
`validate_review` and `record_reproduction` for maintainer scripts. They do not
upload evidence or change GitHub by themselves.

# Review a leaderboard submission

Maintainers review the model setup and rescore every submitted task before
accepting a result. Accepted results are labelled **Contributor evaluated**.
Tasks independently rerun by a maintainer are labelled **Reproduced by BEND**.

Use `bend2 admin --help` to list the review and website-build commands.

## Rescore the evidence

Use BEND installed from the publication branch, independently of the contributor's
PR. Download the linked evidence ZIP and contribution JSON, then run:

```bash
bend2 admin rescore-submission submissions/community-IDENTITY.json \
  --bundle /path/to/downloaded/submission.zip \
  --output reviews/community-IDENTITY.json \
  --cache-dir /path/to/benchmark-cache
```

The command reads the ZIP without executing its code. It checks archive hashes
and protocols, then recomputes scores using the installed benchmark's labels
and cohorts:

| Task | Independently checked from prediction evidence |
| --- | --- |
| Sequence prior | All 512 windows, hidden bases, query probabilities, within-window loss, accuracy and block bootstrap |
| OpenSplice and context | Complete record IDs, trusted targets, group/fold membership, group correlations and macro bootstrap |
| Background | Both trusted state means, paired contrasts, fold membership, group correlations and bootstrap |
| Repair | Frozen requests and candidate menus, direct-swap targets, nominated edits, measured percentile ranks and element bootstrap |
| Cell-selective design | Full candidate menus, no-edit and tied decisions, trusted measured outcomes, nested aggregation and locus bootstrap |
| Atlas | All candidate IDs, 16 requests, 10 choices per request, intended comparison cohorts and both measured replicate gains |
| Tissue identification | Common test genes, trusted expression profiles, tissue retrieval and all 10,000 whole-gene bootstrap draws |

A receipt is written after all tasks pass. Missing records, duplicates,
altered labels, incorrect selections or mismatched scores fail the review.
Undefined groups follow each task's scoring rules. Recomputed metrics must
agree within an absolute tolerance of `1e-10` in the task's units; selection
and ranking rules are unchanged.

Rescoring runs on a CPU. The first intervention review may download the source
datasets; later reviews use the cache. GTEx uses bundled labels and gene IDs,
so it needs neither the genome download nor `py2bit`. Its bootstrap can take
several minutes.

The receipt records hashes of the contribution, evidence and scorer source,
along with the tasks checked, recomputed metrics and time. A change to the
contribution or archive requires a new receipt. Rescore corrections to a new
output path, review them, then replace the old receipt while preserving any
reproduction history.

`bend2 admin validate-submission --bundle ...` checks metadata and file integrity
without rescoring. Rescoring verifies results from the supplied predictions;
it cannot establish which weights ran, how the readout was fitted, or whether
labels leaked into training. Validation-loss grids are checked for consistency;
refitting requires a model rerun.

## Review and accept

Review the checkpoint, adapter, representation, pooling, input handling, fitting
procedure and training-data disclosure. Confirm that the model uses each task's
full input. Resolve discrepancies in the PR before publication.

Generate the receipt using your installed benchmark. Add it under `reviews/`
with the same filename as the contribution, then review and merge both. Receipts
are unsigned JSON files; acceptance depends on maintainer review on the protected
publication branch.

Before public launch, require maintainer and code-owner review and passing CI
on the publication branch. Configure approvals to be dismissed after changes.
`CODEOWNERS` lists the reviewers; enable these requirements in GitHub's branch
settings. Deploy from the publication branch after merge. Run contributed
adapters in isolated jobs, outside privileged CI and cluster login nodes.

The website build reads saved receipts and requires one for every community
record. To preview a PR before review:

```bash
BEND2_PREVIEW_SUBMISSIONS=1 npm --prefix website run build
```

PR CI uses this flag. Preview builds label every community row and task
**Awaiting review**, including entries with a proposed receipt. Push builds
require matching receipts. Stale or malformed receipts fail either build.
Paper results and reference-score anchors stay fixed.

## Independently reproduce selected tasks

Rerun reference examples, leading or surprising results, entries with unresolved
setup questions, and a random sample of other contributions. Select tasks based
on the question and available compute. Other entries can be accepted after
rescoring and setup review. Withhold or withdraw entries with unresolved
material discrepancies, keeping the correction history in their PRs.

After inspecting the adapter and dependencies, run it in an isolated job on
Lumi or another suitable machine. Use a new result directory and a **fresh
inference cache**, with the same weights and declared model configuration.
You can share a verified source-data mirror. Recompute embeddings or
probabilities from the model when recording an independent reproduction.

Export the run with `bend2 export`, host its ZIP, then record the tasks you reran:

```bash
bend2 admin record-reproduction submissions/community-IDENTITY.json \
  --review reviews/community-IDENTITY.json \
  --run results/independent-rerun --tasks atlas_profile \
  --evidence-url https://example.org/independent-rerun.zip \
  --reviewer YOUR_GITHUB_HANDLE \
  --notes "Independent job; pinned weights; fresh inference cache; hardware and setup details" \
  --attest-independent
```

The command checks model identity, rejects reuse of the submitted run, rescores
the rerun, and compares metrics and intervals. The absolute tolerance is `1e-4`
in each metric's units, including percentage points for percentage metrics.
Atlas also checks both replicate gains. Investigate larger differences before
accepting a reproduction. The leaderboard keeps the contributor's score and
links the rerun estimate and evidence in the task's details.

Review the job provenance before attesting to an independent run: files with
edited metadata can pass the software checks. Training-data contamination remains
possible even when a rerun agrees.

For scripts, use `bend2.reviews.rescore_submission`, `validate_review` and
`record_reproduction`. These functions operate on local files.

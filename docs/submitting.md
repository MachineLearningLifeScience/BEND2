# Add your model to the leaderboard

Evaluate any supported subset of the eight tasks, publish the evidence bundle,
and open a pull request containing **one generated JSON file**. You do not need
to add model code to BEND, upload weights to this repository, or run every task.

A pull request is the submission and its review history. Merging it adds the
row on the next website build. Results remain linked to their exact evidence;
there is no account, separate submission service, or spreadsheet to maintain.

## 1. Evaluate and export

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 export results/my-model
```

The model declaration must identify the exact checkpoint revision, training
data, representation and pooling. Prior results also need the probability
interface. Use a weight hash or immutable checkpoint revision; `main` or
`latest` does not identify the weights you evaluated. Describe known overlap
with benchmark sequences or labels in `training_data`.

`submission.zip` contains the scores, protocols, model declaration, prediction
tables and the entry-point `model.py` when supplied. It excludes weights,
embedding caches and raw input sequences. If your adapter imports local helper
modules, publish those alongside it and provide the implementation URL below.
Inspect the files and the [source-data terms](data.md) before sharing them.
New runs also include the small installed benchmark implementation and its
hashes, so a development-version result retains the exact evaluation code.

## 2. Publish the evidence and generate the contribution

Upload `submission.zip` to a durable public download location, such as a
versioned Zenodo record, a Hugging Face repository revision, or a GitHub release
asset. Keep the published bytes unchanged. The contribution includes its SHA256,
so a changed artifact will fail verification even if its URL stays the same.
Use the file download URL, not a landing page.

```bash
bend2 submit results/my-model \
  --evidence-url https://example.org/releases/v1/submission.zip \
  --model-url https://huggingface.co/your-lab/your-model \
  --adapter-url https://github.com/your-lab/your-model/tree/COMMIT/benchmark
```

Replace the example URLs with your actual public links. `--model-url` can be
omitted when the model's `source` declaration contains it. `--adapter-url` is
required for notebook runs without a saved adapter and is also useful when
`model.py` needs supporting files.

This writes `community-<model>-<identity>.json` beside your results. The command
checks the complete frozen cohorts, metric units, scientific protocols and
bundle hashes. The identity is based on the model declaration and adapter,
not a run's date, machine, batch size or task subset.

You can do the same from Python:

```python
from bend2.submissions import prepare_submission

path = prepare_submission(
    result,
    evidence_url="https://example.org/releases/v1/submission.zip",
    model_url="https://huggingface.co/your-lab/your-model",
    adapter_url="https://github.com/your-lab/your-model/tree/COMMIT/benchmark",
)
```

Publishing the evidence is an explicit step. BEND does not upload anything or
open a pull request on your behalf.

## 3. Open the pull request

Add the generated file under [`submissions/`](../submissions/) and open a pull
request targeting `benchmark`. Change only that file for an ordinary model
submission. Leave the prediction files in the evidence bundle; do not commit
ZIP files, Parquet files, model code or weights to the submission directory.

You can use GitHub's **Add file → Upload files** in the submissions directory
without cloning the repository. GitHub will guide you through a fork and pull
request when needed. Include any context a reviewer should know, especially
training-data overlap or sequence-context limitations. The JSON already
contains the scores, coverage and model details; do not retype them in a table.

For more tasks from the same model, resume the existing run, export its enlarged
bundle, and replace the same contribution file in a new PR. A different
checkpoint, representation, pooling method or adapter produces a distinct ID.
This keeps different evaluated model interfaces from silently replacing each
other.

### Prefer an issue?

Open the [model submission issue form](https://github.com/yhsure/genomic-bending/issues/new?template=model.yml)
and attach the generated JSON plus the evidence link. A maintainer can make
the one-file PR for you. The same review and validation apply.

GitHub currently limits ordinary issue attachments to 25 MB, so full benchmark
bundles often need external hosting. A small ZIP can be attached to an issue or
PR and its attachment URL used as the evidence URL. Public access follows the
repository's visibility. [GitHub attachment documentation](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files).

## What gets displayed

Each contributed model has all eight task cells. Unrun tasks stay missing and
retain their explanation. An undefined metric is not replaced by zero and
cannot be submitted as a completed endpoint. Raw estimates and available
bootstrap intervals remain in the contribution.

The site displays community rows separately identifiable from the frozen paper
results. Its optional reference index uses the existing frozen baselines and
reference model, the same display precision, and the same missing-task policy.
Adding a submission does not recompute the paper's results or change its anchors.
An embedding result remains a fitted-readout result; a native probability result
keeps the declared probability interface.

## Maintainer review

1. Check the PR changes only its intended contribution file. Use the trusted
   benchmark code to validate it:

   ```bash
   bend2 validate-submission submissions/community-MODEL-IDENTITY.json \
     --bundle /path/to/downloaded/submission.zip
   ```

   Download the evidence URL from the contribution first. Validation reads the
   ZIP in place and checks its SHA256, recorded run identity, protocol, cohort
   hashes and every declared evidence artifact. It does not import or execute
   the submitted adapter. Validation without `--bundle` checks the contribution
   metadata only; that is useful in a PR check but is not evidence review.

2. Review the checkpoint, adapter, context handling and training-data disclosure.
   Check prediction-level evidence for the reported endpoints. Recorded hashes
   establish consistency; they do not prove which weights ran or absence of
   label leakage. Request corrections in the same PR if needed.

3. Approve and merge. A submission cannot set an `accepted` flag itself. The
   publication branch's reviewed `submissions/` files define the community rows.
   Build the website from `website/data/benchmark.paper.json` plus those files; keep
   the frozen reference data unchanged.

Use a required maintainer review on the publication branch and publish only
from that branch. A PR preview can include a candidate row for inspection,
but should not deploy it to the public leaderboard. These are repository
settings/deployment choices, not a status field provided by the contributor.
[GitHub protected branch documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

The repository's `benchmark.yml` workflow checks the three contributor workflows
and builds the website on pull requests. The build validates every contribution's
metadata and protocol; it does not download external evidence or execute model
adapters. Evidence review remains the explicit maintainer step above.

The website build is deterministic and additive. Removing a community JSON in
a reviewed PR removes its row on the next build. Corrections and withdrawals
therefore remain visible in Git history.

# Add your model to the leaderboard

Evaluate any supported subset of the eight tasks, then submit it with one
command. BEND publishes the evidence and opens a pull request containing
**one generated JSON file**. You do not need to clone BEND,
add model code to its repository, upload weights, or run every task.

A pull request is the submission and its review history. Maintainers independently
rescore every submitted task against trusted benchmark labels, review the model
setup, and add a review record before merging. The row appears on the next
website build. Results remain linked to their exact evidence;
there is no account, separate submission service, or spreadsheet to maintain.

## The shortest path

Install [GitHub CLI](https://cli.github.com/) and authenticate once with
`gh auth login`. After BEND's public release, the standard path is:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 submit results/my-model --github \
  --model-url https://huggingface.co/your-lab/your-model
```

`--github` creates or reuses your BEND fork, hosts the evidence there as a
release asset, and opens the one-file PR against `benchmark`. You do not need
to choose another repository or manage a fork manually. It prints the PR URL.
The release is marked as a prerelease and does not replace the latest release.

**During private development**, the default fork cannot provide public evidence.
Use an existing public repository you can write to instead:

```bash
bend2 submit results/my-model --github your-lab/your-model \
  --model-url https://huggingface.co/your-lab/your-model
```

The explicit repository is also an option after public release, for contributors
who prefer their model or results repository. The BEND repository owner must
use this form because GitHub cannot create a personal fork of their own repository.

Both forms are explicit publishing actions: they upload evidence, create a
contribution branch and open a PR. GitHub CLI manages authentication; no BEND
account or separate token is needed. Repository visibility and default branches
are never changed. Local evaluation and export do not publish anything.

If an upload or network request is interrupted, rerun the same command. Release
names include the complete evidence SHA256; existing assets are verified and
never replaced. The PR branch derives from the generated contribution's bytes,
so an unchanged submission reuses the same PR. Progress and links are also saved
in `results/my-model/github-submission.json`. A closed PR is returned for you to
review, rather than silently opened again.

For notebook runs:

```python
from bend2.github import publish_submission

submission = publish_submission(
    result,
    evidence_repository="your-lab/your-model",  # Omit to use your fork after public release.
    model_url="https://huggingface.co/your-lab/your-model",
    adapter_url="https://github.com/your-lab/your-model/tree/COMMIT/benchmark",
)
print(submission["url"])
```

The GitHub helper is optional. Evaluation, export and the manual submission
workflow below work without GitHub CLI and do not publish anything.

### Evaluated on separate machines?

Bring the result directories together and combine them before submitting:

```bash
bend2 combine results/my-model-atlas results/my-model-prior \
  --output results/my-model
bend2 submit results/my-model --github your-lab/your-model \
  --model-url https://huggingface.co/your-lab/your-model
```

Both runs must use the same checkpoint, representation, preprocessing and
adapter. Combining copies the completed task evidence without running your
model again. The bundle keeps each original run's environment, source code and
provenance. Conflicting results for an overlapping task require resolution;
BEND does not choose a score. The Python equivalent is
`result = bend2.combine([atlas_result, prior_result], output="results/my-model")`.

## What to declare and share

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
Runs retain the exact benchmark source for each task, including tasks added
after a compatible package update. The export includes those source snapshots.

## Manual submission or other evidence hosting

Export a completed run to create `submission.json` and `submission.zip`:

```bash
bend2 export results/my-model
```

The Python equivalent is `result.bundle()`. `submit --github` also exports
automatically.

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

This writes `community-<identity>.json` beside your results. The command
checks declared cohort fingerprints, metric units, scientific protocols and
bundle hashes. The identity follows the checkpoint, representation,
preprocessing and adapter. Changing the display name, descriptive metadata,
adapter's file location, batch size or evaluated task subset keeps the same
contribution filename.

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

Without `--github`, this command writes a local contribution file only. It does
not upload anything or open a pull request.

### Open the pull request

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

With `--github`, rerun the submission command after evaluation finishes. The new
bundle gets a new release and the new PR updates the same model's JSON file.
Review or close an earlier pending PR before submitting a replacement, so there
is one current proposal for that model.

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

Accepted community results are labelled **Contributor evaluated**. Every submitted
task has been independently rescored from its predictions against trusted labels.
Selected tasks that a BEND maintainer also independently reruns are labelled
**Reproduced by BEND**, with the rerun evidence linked on that task. Other tasks
keep their contributor-evaluated label. Neither label establishes absence of
training-data overlap or benchmark contamination.

The site keeps community rows distinguishable from the frozen paper results. Its optional reference index uses the existing frozen baselines and
reference model, the same display precision, and the same missing-task policy.
Adding a submission does not recompute the paper's results or change its anchors.
An embedding result remains a fitted-readout result; a native probability result
keeps the declared probability interface.

## What review asks of you

Run the frozen benchmark with an immutable checkpoint and the documented model
interface. Keep your adapter reproducible and disclose known training-data or
benchmark overlap in the existing model declaration. The CLI includes your
predictions, decisions, protocol and code in the exported evidence automatically.
No additional hand-written score table or reviewer receipt is required from you.

Maintainers check the complete cohorts, labels, decisions, metrics and confidence
intervals independently. They also review the adapter, pooling, context handling
and fitting setup. A score can be internally consistent and still come from the
wrong model or a leaked readout; prediction-only checks cannot establish execution.
Selected entries may therefore be independently rerun, including leading or
unusual results and random audits. Be prepared to clarify the setup or help make
it reproducible. Publication does not wait for every model to enter a BEND compute
queue.

The [maintainer guide](reviewing.md) describes rescoring, acceptance and selective
reproduction. The public website builds from reviewed records on the publication
branch. PR previews mark unreviewed candidates explicitly; they are not accepted
leaderboard entries. Corrections require a new matching review record. Withdrawals
remove the submission and its review in a reviewed PR, preserving their history.

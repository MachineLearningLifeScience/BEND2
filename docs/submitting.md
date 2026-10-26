# Add your model to the leaderboard

You can submit results for any subset of the eight tasks. The submission is a
pull request containing a generated JSON file, with a link to the prediction
files used to calculate the scores.

Maintainers rescore each task against the benchmark labels and review the model
setup before merging. Accepted results appear on the next website build.

## The shortest path

Install [GitHub CLI](https://cli.github.com/) and authenticate once with
`gh auth login`. After BEND's public release, the standard path is:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 submit results/my-model --github \
  --model-url https://huggingface.co/your-lab/your-model
```

`--github` creates or reuses your BEND fork, uploads the evidence as a prerelease
asset, and opens a PR against `benchmark`. It prints the PR URL.

**During private development**, the default fork cannot provide public evidence.
Use an existing public repository you can write to instead:

```bash
bend2 submit results/my-model --github your-lab/your-model \
  --model-url https://huggingface.co/your-lab/your-model
```

You can also choose a repository after public release. The BEND repository
owner must use this form because GitHub cannot create a personal fork of their
own repository. GitHub CLI handles authentication for the upload and PR.

If a network request is interrupted, rerun the command. BEND checks existing
uploads by SHA256 and reuses the PR for an unchanged submission. Progress and
links are saved in `results/my-model/github-submission.json`. If the PR is
closed, the command returns its link for you to review.

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

### Evaluated on separate machines?

Bring the result directories together and combine them before submitting:

```bash
bend2 combine results/my-model-atlas results/my-model-prior \
  --output results/my-model
bend2 submit results/my-model --github your-lab/your-model \
  --model-url https://huggingface.co/your-lab/your-model
```

Both runs must use the same checkpoint, representation, preprocessing and
adapter. Combining copies the completed results and preserves each run's
environment and source code. Resolve conflicting results for overlapping tasks
before combining. The Python equivalent is
`result = bend2.combine([atlas_result, prior_result], output="results/my-model")`.

## What to declare and share

Record the checkpoint revision, training data, representation and pooling in
the model declaration. Prior results also need the probability interface. Use
a weight hash or immutable checkpoint revision, and describe known overlap with
benchmark sequences or labels in `training_data`.

`submission.zip` contains scores, protocols, model declarations, prediction
tables, benchmark source snapshots and the entry-point `model.py` when supplied.
Weights, embedding caches and raw sequences stay local. If your adapter imports
local helper modules, publish those alongside it and provide their URL below.
Inspect the bundle and [source-data terms](data.md) before sharing it.

## Manual submission or other evidence hosting

Export a completed run to create `submission.json` and `submission.zip`:

```bash
bend2 export results/my-model
```

The Python equivalent is `result.bundle()`. `submit --github` also exports
automatically.

Upload `submission.zip` to a versioned Zenodo record, Hugging Face repository
revision, GitHub release or another public download location. Use a direct file
download URL and keep the uploaded file unchanged: the submission records its
SHA256 checksum.

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

This writes `community-<identity>.json` beside your results after checking the
cohort, metric units, protocol and bundle hashes. The filename identifies the
checkpoint, representation, preprocessing and adapter. It stays the same when
you add tasks, change descriptive metadata, move the adapter or adjust batch size.

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

Without `--github`, the file is saved locally for you to upload in a PR.

### Open the pull request

Add the generated JSON under [`submissions/`](../submissions/) in a pull request
targeting `benchmark`. Keep prediction files in the hosted bundle.

GitHub's **Add file → Upload files** lets you do this in the browser. Include any
context a reviewer should know, especially training-data overlap or input-length
limitations. Scores, task coverage and model details are already in the JSON.

To add tasks for the same model, resume the run, export the updated bundle,
and replace the contribution file in a new PR. Changing the checkpoint,
representation, pooling or adapter produces a new ID.

With `--github`, rerun the submission command after evaluation finishes. The new
bundle gets a new release and the new PR updates the same model's JSON file.
Review or close an earlier pending PR before submitting a replacement, so there
is one current proposal for that model.

### Prefer an issue?

Open the [model submission issue form](https://github.com/yhsure/genomic-bending/issues/new?template=model.yml)
and attach the generated JSON plus the evidence link. A maintainer can open
the PR for you. The same review and validation apply.

For a ZIP small enough to attach to a public issue or PR, you can use its
attachment URL as the evidence URL. See [GitHub's attachment limits](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files).

## What gets displayed

The leaderboard shows a score and available bootstrap interval for each
submitted task. Other cells show the reason the task was not evaluated.
Only tasks with defined metrics can be submitted as completed results.

Accepted community results are labelled **Contributor evaluated**. Every submitted
task has been independently rescored from its predictions against trusted labels.
Selected tasks that a BEND maintainer also independently reruns are labelled
**Reproduced by BEND**, with the rerun evidence linked on that task. Other tasks
keep their contributor-evaluated label. Neither label establishes absence of
training-data overlap or benchmark contamination.

Community rows are labelled separately from paper results. The optional reference
index uses the paper's baselines and reference model. Task details identify the
fitted readout or declared probability interface used for each result.

## What review asks of you

Use an immutable checkpoint and the documented model interface. Publish enough
adapter code to repeat the run and disclose known benchmark overlap. Maintainers
may ask about pooling, input handling, fitting or training data.

Rescoring checks the submitted predictions, decisions and measurements. To check
model execution, maintainers rerun selected entries, including leading or unusual
results and a random sample. Maintainers may ask for help reproducing your setup.

The [maintainer guide](reviewing.md) describes acceptance and reproduction. PR
previews label candidates **Awaiting review**. Corrections need an updated review
record; withdrawals remove the submission and review through a PR, keeping the
history on GitHub.

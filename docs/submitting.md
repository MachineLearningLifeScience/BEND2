# Add your model to the leaderboard

You can submit results for any subset of the eight tasks. The submission is a
pull request containing a generated JSON file, with a link to the prediction
files used to calculate the scores.

Maintainers rescore each task against the benchmark labels and review the model
setup before merging. Accepted results appear on the next website build.

## Submit a result

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

The BEND repository owner must also specify a repository. If an upload is
interrupted, rerun the command; unchanged uploads and PRs are reused.
Progress and links are saved in `results/my-model/github-submission.json`.

## What to declare and share

Record the checkpoint revision, training data, representation and pooling in
the model declaration. Prior results also need the probability interface. Use
a weight hash or immutable checkpoint revision, and describe known overlap with
benchmark sequences or labels in `training_data`.

`submission.zip` contains scores, protocols, model declarations, prediction
tables, benchmark source snapshots and the entry-point `model.py` when supplied.
Weights, embedding caches and raw sequences stay local. If your adapter imports
local helper modules, publish those alongside it and pass `--adapter-url URL` to
`bend2 submit`. This option is required for notebook runs without a saved adapter.
Inspect the bundle and [source-data terms](data.md) before sharing it.

## Host evidence elsewhere

Export a completed run to create `submission.json` and `submission.zip`:

```bash
bend2 export results/my-model
```

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

Add the generated `community-<identity>.json` under [`submissions/`](../submissions/)
in a PR targeting `benchmark`. Keep ZIPs, prediction files, model code and weights
outside this repository. If you need help opening the PR, attach the JSON to the
[model submission issue form](https://github.com/yhsure/genomic-bending/issues/new?template=model.yml).

## Update a submission

To add tasks, resume the run and repeat the submission command. Use `bend2 combine`
first if you evaluated tasks in separate directories. The generated filename
stays the same for the same checkpoint, representation, preprocessing and adapter.
With manual hosting, upload the new bundle and replace the JSON in a new PR.
Review or close an earlier pending PR before submitting a replacement, so there
is one current proposal for that model.

## Review

Accepted community results are labelled **Contributor evaluated**. Every submitted
task has been independently rescored from its predictions against trusted labels.
Selected tasks that a BEND maintainer also independently reruns are labelled
**Reproduced by BEND**, with the rerun evidence linked on that task. Other tasks
keep their contributor-evaluated label. Neither label establishes absence of
training-data overlap or benchmark contamination.

Maintainers may ask about pooling, input handling, fitting or training data, or
for help reproducing your setup. They rerun selected entries, including leading
or unusual results and a random sample.

The [maintainer guide](reviewing.md) describes acceptance and reproduction. PR
previews label candidates **Awaiting review**. Corrections need an updated review
record; withdrawals remove the submission and review through a PR, keeping the
history on GitHub.

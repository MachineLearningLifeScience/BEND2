# Submit a model

You can contribute any supported subset of tasks. You do not need to fork
the repository, add your model to a registry, or upload its weights.

## Create the bundle

After running your model:

```bash
bend2 export results/my-model
```

Or from Python:

```python
bundle = result.bundle()
```

Check `submission.json` for the model name, checkpoint revision, training-data
declaration, representation, and pooling. Local exploratory runs can omit
metadata, but an incomplete model declaration is not ready for leaderboard
review. Correct the declaration in the model source and produce the result
under that identity before submitting.

The ZIP contains the submission summary and the task evidence needed to
inspect the result, including predictions and measured labels. For a CLI
model file, it also includes the saved adapter source. It excludes
model weights, raw DNA inputs, and large embedding caches. Review the files
before sharing them.

## Request a leaderboard row

Open a [model-submission issue](https://github.com/yhsure/genomic-bending/issues/new)
and attach `submission.zip`. Include:

- A checkpoint or model page, with the exact evaluated revision.
- Your adapter source, either included in the bundle or linked from the issue.
- Pretraining and subsequent training data, including any known benchmark
  overlap.
- The tasks you evaluated and any model-interface limitations.

The saved adapter is its entry-point file. If it imports local helper modules,
link that implementation as well.

If the artifact is too large for an issue attachment, provide a stable
download link. The adapter and weights can have their own licenses; describe
access requirements clearly.

Submission is currently reviewed through GitHub. The package does not
upload to the website or automatically accept a row. Maintainers review
the declaration, task coverage, provenance, and score evidence before
importing the result into the leaderboard.

## What the scores mean

Every submission accounts for all eight task IDs. Unrun tasks have no score
and an explanation. An undefined metric is also identified, rather than
converted to zero. Scores retain their original units and direction; BEND
does not compute an overall score.

An embedding adapter produces **fitted-readout** results. A native nucleotide
probability callback produces a sequence-prior result under its declared
probability interface. The declaration must preserve that distinction when
the website displays the model.

Prediction-level evidence helps a reviewer inspect calculations. It does
not independently prove which weights ran or what data they saw. Training
history, allowed sequence context, pooling, and any native-head supervision
remain part of the comparison.

## For maintainers

Keep the validated bundle alongside the accepted row. Confirm that the model
revision and declared interfaces match the evaluated results, retain missing
tasks, and preserve metric units. Review source-dataset terms when sharing
the prediction-level artifacts. Do not execute an unfamiliar adapter merely
to preview its submission.

`submission.json` is the machine-readable handoff. A website integration
should consume its raw endpoints and coverage, preserving missing values.
Acceptance remains a separate editorial action.

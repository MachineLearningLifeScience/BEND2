# Preparing a result for review

Evaluate a model locally and export its predictions and setup:

```bash
draft run my_model.py --tasks atlas_profile --output results/my-model
draft export results/my-model
```

Keep the adapter, exact model revision and inference settings with the result.
The archive includes the predictions needed to check the scores. To prepare the contribution JSON for local rescoring, use an evidence URL
approved for anonymous review:

```bash
draft submit results/my-model --evidence-url https://example.org/anonymous-evidence.zip
```

Replace the example URL with the location of your exported archive. This writes
a local contribution record; it does not open a pull request. See
[reviewing](reviewing.md) for independent rescoring.

Public GitHub uploads and automatic pull requests are disabled in this edition.
Share the exported archive through the submission venue's approved anonymous
mechanism. Remove identifying paths and model-owner metadata from your own
adapter and result description before sharing.

# Community model submissions

**One model/interface, one generated JSON file, one pull request.**

Follow [the submission guide](../docs/submitting.md). Generate the file with
`bend2 submit`, then add it here without editing its metrics. Predictions and
other large evidence stay in the linked, SHA256-identified ZIP.

Files are named `community-<model-name>-<identity>.json`. Each records:

- The immutable model/checkpoint declaration and adapter identity.
- A public evidence download URL, file size and SHA256.
- Raw task metrics, exact protocol and cohort identities, and evidence hashes.
- Coverage and an explanation for every task not evaluated.

The file format is validated by `bend2.submissions.validate_submission`. It has
no acceptance field. Maintainer review and merge are the acceptance event; a
website build reads these files from the publication branch and adds their rows
to the frozen reference data.

Do not add example results here: every JSON in this directory becomes a
community row in a build. No ZIPs, predictions, model implementations or weights
belong in this directory. Use the issue form if you prefer a maintainer to open
the PR for you.

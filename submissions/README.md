# Community model submissions

**One model/interface, one generated JSON file, one pull request.**

Follow [the submission guide](../docs/submitting.md). Generate the file with
`bend2 submit`, then add it here without editing its metrics. Predictions and
other large evidence stay in the linked, SHA256-identified ZIP.

Files are named `community-<16-character-identity>.json`. The identity follows
the checkpoint, representation and inference implementation. Correcting the
display name, training-data description or model URL does not create a second
row. Moving an adapter between computers does not change its identity.
Each file records:

- The immutable model/checkpoint declaration and adapter identity.
- A public evidence download URL, file size and SHA256.
- Raw task metrics, exact protocol and cohort identities, and evidence hashes.
- Coverage and an explanation for every task not evaluated.

The file format is validated by `bend2.submissions.validate_submission`. It has
no acceptance field. Maintainer review and merge are the acceptance event; a
website build reads these files from the publication branch and adds their rows
to the frozen reference data.

Update the same file when adding tasks for the same model configuration. Use
`bend2 combine` first if those tasks were evaluated in separate result
directories. The website build rejects duplicate model configurations, including
duplicates presented under different display names. Historical generated
filenames remain readable, but new contributions use the stable identity.
Older runs without inference-specific fingerprints retain conservative full-source
identity: comments or metadata edits inside their adapter source may require a
new result manifest before BEND can establish that inference is unchanged.

Do not add example results here: every JSON in this directory becomes a
community row in a build. No ZIPs, predictions, model implementations or weights
belong in this directory. Use the issue form if you prefer a maintainer to open
the PR for you.

Publication also requires a matching maintainer-generated receipt in `reviews/`.
Contributors do not add their own acceptance or reproduction status. See the
[review guide](../docs/reviewing.md) for trusted rescoring and selective reruns.

# Community model submissions

Generate a contribution with `bend2 submit` and add its JSON file here in a
pull request. See [the submission guide](../docs/submitting.md) for exporting
and hosting the prediction files.

Files are named `community-<16-character-identity>.json`. The ID depends on
the checkpoint, representation and inference implementation. It stays the same
when you edit descriptive metadata or move the adapter. Each file records:

- Model and checkpoint declarations, including the adapter identity.
- A public evidence URL, file size and SHA256 checksum.
- Task scores, protocols, cohort identities and evidence hashes.
- The reason for each task not evaluated.

Update the same file when adding tasks for the same model configuration. Use
`bend2 combine` first if the tasks were evaluated in separate directories.
The website build rejects duplicate model configurations, including ones with
different display names. Older filenames remain supported. Runs made before
inference-specific fingerprints were introduced use the full adapter source
for identity, so editing comments or metadata can change their ID.

Each published record also needs a matching maintainer-generated receipt in
`reviews/`. Maintainers add this during review and merge both files. The
[review guide](../docs/reviewing.md) describes rescoring and independent reruns.

Keep only submitted JSON records here. The website build reads every JSON in
this directory, so examples belong elsewhere. Host ZIPs and prediction
files at the evidence URL; model code and weights belong with the model.

# Maintainer review records

Each published community submission needs a matching `<model-id>.json` here.
The file records trusted rescoring of every submitted task and any independent
model reruns, with evidence hashes. Generate it with `bend2 admin rescore-submission`;
see [the maintainer guide](../docs/reviewing.md).

Contributors only submit their generated file in `submissions/`. A maintainer
generates and reviews this record using a trusted benchmark checkout, then adds
it to the PR before merging. A receipt is evidence of checks, not a signature
or a self-service approval. Protect this directory with required code-owner
review on the publication branch. A changed submission or evidence archive
invalidates the receipt.

Keep actual result ZIPs outside Git. No example or synthetic acceptance records
belong in this directory.

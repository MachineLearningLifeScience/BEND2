# Maintainer review records

Each published community submission needs a matching `<model-id>.json` here.
Generate it with `bend2 admin rescore-submission` from a trusted benchmark
installation. The file records rescoring of every submitted task, any independent
model reruns, and evidence hashes. See [the review guide](../docs/reviewing.md).

A maintainer adds the receipt to the contribution's PR before merging. Receipts
are unsigned JSON; require code-owner review for this directory on the
publication branch. Changing the submission or evidence archive requires an
updated receipt.

Store result ZIPs outside Git. Keep this directory for actual review records.

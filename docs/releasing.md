# Publishing BEND 2.0

The code, Python package and leaderboard are released from this repository.
Versioned benchmark inputs remain on Hugging Face; their revisions and checksums
are recorded in `src/bend2/assets.json`.

## Website

Enable GitHub Pages in the repository settings and choose **GitHub Actions** as
the source. The `Deploy GitHub Pages` workflow publishes the website from `main`
at <https://machinelearninglifescience.github.io/BEND2/>. It can also be run
manually. The workflow tests the benchmark and builds reviewed submissions
before deploying.

## PyPI with the local credential

The first release uses the existing PyPI token in macOS Keychain, stored for
`https://upload.pypi.org/legacy/` with username `__token__`. Twine reads it directly;
do not put the token in a command, file or repository secret.

```bash
python -m build
python -m twine check --strict dist/*
TWINE_USERNAME=__token__ python -m twine upload --non-interactive dist/*
```

Use a clean `dist/` containing only the intended version. Test installation from
the built wheel before uploading.

## Optional GitHub trusted publishing

To activate the prepared `Publish to PyPI` workflow, add a GitHub trusted
publisher in the `bend2` project's PyPI settings with these exact values.
For a project that does not exist yet, use a pending publisher at
<https://pypi.org/manage/account/publishing/> instead.

| Field | Value |
| --- | --- |
| PyPI project name | `bend2` |
| GitHub owner | `MachineLearningLifeScience` |
| Repository | `BEND2` |
| Workflow filename | `publish.yml` |
| Environment | `pypi` |

Create the `pypi` GitHub environment with a maintainer as a required reviewer.
Publishing uses short-lived GitHub credentials; no PyPI API token is stored in
the repository. See [PyPI's setup instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## Release a version

1. Update the version in `pyproject.toml`, `CITATION.cff` and `src/bend2/__init__.py`.
2. Confirm the benchmark tests and website build pass.
3. Create a `vVERSION` tag and a GitHub release with brief release notes for the same commit.
4. Upload locally, or run `Publish to PyPI` with that tag after trusted
   publishing is configured and approve its `pypi` environment deployment.

The publishing workflow builds the source distribution and wheel, checks their
metadata, installs the wheel and runs the workflow tests. A separate job uploads
those artifacts and their provenance attestations to PyPI. This workflow is
manual; creating a GitHub release does not trigger an upload.

After publication, verify installation from PyPI in a fresh environment.
The package can be released before the website. PyPI does not allow replacing an uploaded version;
package corrections need a new version.

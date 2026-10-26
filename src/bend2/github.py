"""Optional, restartable GitHub handoff using the contributor's installed ``gh``.

Only :func:`publish_submission` changes remote state. It hosts evidence in the
repository the caller names and proposes one data file against ``benchmark``.
Credentials stay with GitHub CLI; model code is never imported here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from filelock import FileLock

from bend2.results import Run, digest, write_json
from bend2.submissions import prepare_submission

UPSTREAM = "yhsure/genomic-bending"
BASE = "benchmark"
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+\Z")


class _GitHubError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class _GitHub:
    def __init__(self):
        self.executable = shutil.which("gh")
        if not self.executable:
            raise ValueError("Install GitHub CLI from https://cli.github.com and run gh auth login")

    def command(self, arguments, *, payload=None, output=None):
        environment = os.environ.copy()
        environment.pop("GH_DEBUG", None)
        environment["GH_PROMPT_DISABLED"] = "1"
        environment["GH_HOST"] = "github.com"
        try:
            response = subprocess.run(
                [self.executable, *arguments],
                input=None if payload is None else json.dumps(payload).encode(),
                stdout=output if output is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "GitHub request timed out. Rerun the same command to resume safely"
            ) from error
        if response.returncode:
            if response.returncode == 4:
                raise _GitHubError(
                    "GitHub authentication is required. Run gh auth login, then rerun submission"
                )
            match = re.search(rb"HTTP (\d{3})", response.stderr)
            status = int(match[1]) if match else None
            # Do not echo gh's environment, authentication diagnostics or headers.
            message = f"GitHub request failed{f' (HTTP {status})' if status else ''}"
            if status in {401, 403}:
                message += "; check gh authentication and repository permissions"
            else:
                try:
                    detail = json.loads(response.stdout or b"{}").get("message", "")
                    message += f": {detail}" if detail else ""
                except (ValueError, AttributeError):
                    pass
            raise _GitHubError(message + ". Rerun the same command after resolving it", status)
        return response.stdout

    def api(self, endpoint, *, method="GET", payload=None, optional=False):
        arguments = ["api", "--hostname", "github.com", "--method", method, endpoint]
        if payload is not None:
            arguments += ["--input", "-"]
        try:
            raw = self.command(arguments, payload=payload)
        except _GitHubError as error:
            if optional and error.status == 404:
                return None
            raise
        return json.loads(raw) if raw else None


def _verify_asset(github, repository, asset, expected, size):
    if asset.get("state") != "uploaded" or asset.get("size") != size:
        raise ValueError(
            "The existing evidence asset is incomplete or has a different size; it was not replaced"
        )
    recorded = asset.get("digest")
    if recorded:
        if recorded != f"sha256:{expected}":
            raise ValueError(
                "The existing evidence asset has a different SHA256; it was not replaced"
            )
        return
    # Older release assets may have no server-side digest. Compare their bytes.
    with tempfile.TemporaryDirectory(prefix="bend2-evidence-") as directory:
        downloaded = Path(directory) / "submission.zip"
        with downloaded.open("wb") as output:
            github.command(
                [
                    "api",
                    "--hostname",
                    "github.com",
                    "--header",
                    "Accept: application/octet-stream",
                    f"repos/{repository}/releases/assets/{asset['id']}",
                ],
                output=output,
            )
        if digest(downloaded) != expected:
            raise ValueError(
                "The existing evidence download has a different SHA256; it was not replaced"
            )


def _host_evidence(github, repository, metadata, tag, archive, checksum):
    endpoint = f"repos/{repository}/releases/tags/{tag}"
    release = github.api(endpoint, optional=True)
    if release is None:
        commit = github.api(
            f"repos/{repository}/commits/{quote(metadata['default_branch'], safe='')}"
        )
        release = github.api(
            f"repos/{repository}/releases",
            method="POST",
            payload={
                "tag_name": tag,
                "target_commitish": commit["sha"],
                "name": f"BEND 2.0 evidence {checksum[:12]}",
                "body": f"Benchmark evidence archive. SHA256: `{checksum}`.\n\nKeep this asset unchanged so the leaderboard contribution remains verifiable.",
                "draft": False,
                "prerelease": True,
                "make_latest": "false",
            },
        )
    if release.get("draft"):
        raise ValueError(
            "The evidence release is a draft. Publish it before rerunning this command"
        )
    assets = [asset for asset in release.get("assets", []) if asset["name"] == "submission.zip"]
    if not assets:
        # gh interprets '#' in an upload filename as an asset label. A private
        # temporary path also keeps a simultaneous export from changing its bytes.
        with tempfile.TemporaryDirectory(prefix="bend2-upload-") as directory:
            snapshot = Path(directory) / "submission.zip"
            shutil.copyfile(archive, snapshot)
            if digest(snapshot) != checksum:
                raise ValueError(
                    "The local bundle changed while preparing its upload; rerun submission"
                )
            github.command(["release", "upload", tag, str(snapshot), "--repo", repository])
        release = github.api(endpoint)
        assets = [asset for asset in release.get("assets", []) if asset["name"] == "submission.zip"]
    if len(assets) != 1:
        raise ValueError(
            "GitHub did not return exactly one submission.zip asset; rerun to inspect the upload"
        )
    _verify_asset(github, repository, assets[0], checksum, archive.stat().st_size)


def _contributor_repository(github, login):
    if login.lower() == UPSTREAM.split("/")[0].lower():
        return UPSTREAM
    for name in (UPSTREAM.split("/")[1], "bend2-submissions"):
        repository = f"{login}/{name}"
        existing = github.api(f"repos/{repository}", optional=True)
        if existing is None:
            fork = github.api(
                f"repos/{UPSTREAM}/forks",
                method="POST",
                payload={
                    "name": name,
                    "default_branch_only": False,
                },
            )
            return fork["full_name"]
        if existing.get("parent", {}).get("full_name", "").lower() == UPSTREAM.lower():
            return existing["full_name"]
    raise ValueError(
        "Your genomic-bending and bend2-submissions repositories are unrelated to BEND. Use the manual one-file PR workflow"
    )


def _content(github, repository, path, ref):
    return github.api(
        f"repos/{repository}/contents/{path}?{urlencode({'ref': ref})}", optional=True
    )


def _same_content(record, payload):
    return bool(
        record
        and record.get("encoding") == "base64"
        and base64.b64decode(record.get("content", "")) == payload
    )


def publish_submission(
    run,
    evidence_repository,
    *,
    model_url=None,
    adapter_url=None,
    family="",
    parameter_label="",
    progress=None,
):
    """Upload evidence and propose one leaderboard JSON file through GitHub.

    ``evidence_repository`` is an existing, public ``OWNER/REPO`` you can write.
    Calling this function explicitly authorizes its upload, fork, branch and PR.
    Repeating it reuses matching evidence and the existing PR. No clone, shell,
    token handling, force push, default-branch edit or evidence replacement occurs.
    """
    if not isinstance(evidence_repository, str) or not _REPOSITORY.fullmatch(evidence_repository):
        raise ValueError("Provide an existing evidence repository as OWNER/REPO")
    if evidence_repository.lower() == UPSTREAM.lower():
        raise ValueError(
            "Host evidence in your model or results repository, separate from the BEND repository"
        )
    run = run if isinstance(run, Run) else Run(run)
    # Serialise submissions from this result directory without holding an eval lock.
    with FileLock(str(run.directory / ".github-submission.lock"), timeout=0):
        return _publish(
            run,
            evidence_repository,
            model_url=model_url,
            adapter_url=adapter_url,
            family=family,
            parameter_label=parameter_label,
            progress=progress,
        )


def _publish(
    run, evidence_repository, *, model_url, adapter_url, family, parameter_label, progress
):
    notify = progress or (lambda message: None)
    notify("Validating the completed run and preparing its evidence")
    archive = run.bundle()
    checksum = digest(archive)
    tag = f"bend2-{checksum}"
    evidence_url = (
        f"https://github.com/{evidence_repository}/releases/download/{tag}/submission.zip"
    )
    record_path = prepare_submission(
        run,
        evidence_url,
        model_url=model_url,
        adapter_url=adapter_url,
        family=family,
        parameter_label=parameter_label,
    )
    payload = record_path.read_bytes()
    record = json.loads(payload)
    branch = f"bend2/submission-{hashlib.sha256(payload).hexdigest()[:24]}"
    path = f"submissions/{record_path.name}"
    state = {
        "submission_file": str(record_path),
        "evidence_url": evidence_url,
        "evidence_sha256": checksum,
        "branch": branch,
        "status": "prepared",
    }
    journal = run.directory / "github-submission.json"
    write_json(journal, state)
    # All local metadata, scientific protocols and archive bytes have passed
    # validation before even the first authenticated request.
    github = _GitHub()
    login = github.api("user")["login"]
    evidence = github.api(f"repos/{evidence_repository}")
    if evidence.get("private") or evidence.get("visibility", "public") != "public":
        raise ValueError(
            "Choose a public evidence repository; this command never changes repository visibility"
        )
    if evidence.get("archived") or not evidence.get("permissions", {}).get("push"):
        raise ValueError("You need write access to an active evidence repository")
    base = github.api(f"repos/{UPSTREAM}/git/ref/heads/{BASE}")["object"]["sha"]
    if _same_content(_content(github, UPSTREAM, path, BASE), payload):
        state.update(
            status="already_present",
            pull_request_url=None,
            url=f"https://github.com/{UPSTREAM}/blob/{BASE}/{path}",
            repository=UPSTREAM,
        )
        write_json(journal, state)
        return state
    notify(f"Uploading or verifying evidence in {evidence_repository}")
    _host_evidence(github, evidence_repository, evidence, tag, archive, checksum)
    state["status"] = "evidence_uploaded"
    write_json(journal, state)
    repository = _contributor_repository(github, login)
    state["repository"] = repository
    notify(f"Preparing the one-file contribution in {repository}")
    reference = f"repos/{repository}/git/ref/heads/{branch}"
    if github.api(reference, optional=True) is not None:
        previous = github.api(
            f"repos/{UPSTREAM}/compare/{BASE}...{quote(login + ':' + branch, safe='')}"
        )
        if any(item["filename"] != path for item in previous.get("files", [])):
            raise ValueError(f"{branch} contains unrelated changes; it was not modified")
    else:
        # Fork creation is asynchronous; wait briefly for its object store.
        for attempt in range(6):
            try:
                github.api(
                    f"repos/{repository}/git/refs",
                    method="POST",
                    payload={"ref": f"refs/heads/{branch}", "sha": base},
                )
                break
            except _GitHubError as error:
                if github.api(reference, optional=True) is not None:
                    break
                if error.status not in {404, 409, 422} or attempt == 5:
                    raise
                time.sleep(2)
    existing = _content(github, repository, path, branch)
    if not _same_content(existing, payload):
        # A resumed branch can contain only its expected parent version. Never
        # overwrite manual changes made after an earlier submission attempt.
        parent_record = _content(github, UPSTREAM, path, base)
        if existing and (not parent_record or existing["sha"] != parent_record["sha"]):
            raise ValueError(f"{branch} contains a different contribution; it was not overwritten")
        request = {
            "message": f"Submit {record['model']['name']} to BEND 2.0",
            "content": base64.b64encode(payload).decode(),
            "branch": branch,
        }
        if existing:
            request["sha"] = existing["sha"]
        github.api(f"repos/{repository}/contents/{path}", method="PUT", payload=request)
    state["status"] = "contribution_uploaded"
    write_json(journal, state)
    comparison = github.api(
        f"repos/{UPSTREAM}/compare/{BASE}...{quote(login + ':' + branch, safe='')}"
    )
    changed = [item["filename"] for item in comparison.get("files", [])]
    if changed != [path]:
        raise ValueError(
            f"The contribution branch changes files beyond {path}; inspect it before opening a PR"
        )
    query = urlencode({"state": "all", "base": BASE, "head": f"{login}:{branch}", "per_page": 100})
    pulls = github.api(f"repos/{UPSTREAM}/pulls?{query}")
    if pulls:
        pull = pulls[0]
    else:
        notify("Opening the leaderboard pull request")
        pull = github.api(
            f"repos/{UPSTREAM}/pulls",
            method="POST",
            payload={
                "title": f"Add {record['model']['name']} to the BEND 2.0 leaderboard",
                "head": f"{login}:{branch}",
                "base": BASE,
                "body": f"Generated from a completed BEND 2.0 evaluation.\n\nTasks: {', '.join(record['tasks'])}.\n\nEvidence: {evidence_url}\n\nSHA256: `{checksum}`\n\nThe contribution records the checkpoint, adapter, training-data declaration, frozen protocols and raw scores. Please review its evidence before merging.",
                "maintainer_can_modify": True,
            },
        )
    state.update(
        pull_request_url=pull["html_url"],
        url=pull["html_url"],
        status="merged" if pull.get("merged_at") else pull["state"],
    )
    write_json(journal, state)
    return state

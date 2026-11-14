"""Anonymous review transport boundaries and frozen bundled inputs."""

import hashlib
import io
import subprocess
import urllib.request
from urllib.parse import urlsplit

import pytest

from draft import datasets, plan
from draft.cli import main
from draft.github import publish_submission
from draft.model import composition


def test_default_downloads_use_only_original_data_hosts(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("Planning must not trigger network requests")

    monkeypatch.delenv("DRAFT_ASSET_DIR", raising=False)
    monkeypatch.delenv("DRAFT_ASSET_BASE_URL", raising=False)
    monkeypatch.setattr(datasets, "_open_asset", offline)
    expected = {
        "opensplice.tsv.gz": "https://ndownloader.figshare.com/files/64886694",
        "siraj.zip": "https://zenodo.org/api/records/15297965/files/data_satmut.zip/content",
        "hg38.2bit": "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.2bit",
    }
    actual = {
        name: datasets.asset_download_url(name)
        for name, spec in datasets.MANIFEST["files"].items()
        if spec.get("distribution") != "bundled"
    }
    assert actual == expected
    assert all(urlsplit(url).scheme == "https" for url in actual.values())
    proposal = plan(composition(), tasks="opensplice", cache_dir=tmp_path)
    assert proposal["ready"]
    assert proposal["additional_download_bytes"] == 425453242
    assert proposal["assets"][0]["state"] == "download"


@pytest.mark.parametrize("transport", ["local", "https", "upstream"])
def test_configured_assets_enforce_pinned_bytes(tmp_path, monkeypatch, transport):
    payload = b"anonymous review input\n"
    name = "review-fixture.bin"
    spec = {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "upstream_url": "https://example.net/original.bin",
    }
    monkeypatch.setitem(datasets.MANIFEST["files"], name, spec)
    monkeypatch.delenv("DRAFT_ASSET_DIR", raising=False)
    monkeypatch.delenv("DRAFT_ASSET_BASE_URL", raising=False)
    requests = []

    def incoming(request):
        assert transport != "local"
        expected = (
            "https://example.org/review-data/" + name
            if transport == "https" else spec["upstream_url"]
        )
        assert request.full_url == expected
        assert request.get_header("User-agent") == "DRAFT/benchmark"
        requests.append(request.full_url)
        return io.BytesIO(payload)

    monkeypatch.setattr(datasets, "_open_asset", incoming)
    if transport == "local":
        mirror = tmp_path / "mirror"
        mirror.mkdir()
        (mirror / name).write_bytes(payload)
        monkeypatch.setenv("DRAFT_ASSET_DIR", str(mirror))
    if transport != "upstream":
        monkeypatch.setenv("DRAFT_ASSET_BASE_URL", "https://example.org/review-data/")
    result = datasets.asset(name, cache_dir=tmp_path / "cache")
    assert result.read_bytes() == payload
    assert datasets.asset(name, cache_dir=tmp_path / "cache") == result
    assert len(requests) == (0 if transport == "local" else 1)
    result.write_bytes(payload[:-1] + b"!")
    with pytest.raises(ValueError, match="checksum mismatch"):
        datasets.asset(name, cache_dir=tmp_path / "cache")


def test_missing_asset_without_upstream_does_not_guess_a_host(tmp_path, monkeypatch):
    monkeypatch.delenv("DRAFT_ASSET_DIR", raising=False)
    monkeypatch.delenv("DRAFT_ASSET_BASE_URL", raising=False)
    spec = {"bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}
    monkeypatch.setitem(datasets.MANIFEST["files"], "unhosted.bin", spec)
    with pytest.raises(FileNotFoundError, match="No download was attempted"):
        datasets.asset("unhosted.bin", cache_dir=tmp_path)


@pytest.mark.parametrize("url", [
    "http://example.org/file", "file:///tmp/file", "https://user@example.org/file",
    "https://example.org/file#fragment",
])
def test_unsafe_asset_urls_and_redirects_are_rejected(url, monkeypatch):
    monkeypatch.setenv("DRAFT_ASSET_BASE_URL", url)
    with pytest.raises(ValueError, match="HTTPS URL"):
        datasets.asset_download_url("siraj.zip")
    monkeypatch.delenv("DRAFT_ASSET_BASE_URL")
    monkeypatch.setitem(datasets.MANIFEST["files"], "unsafe.bin", {"upstream_url": url})
    with pytest.raises(ValueError, match="HTTPS URL"):
        datasets.asset_download_url("unsafe.bin")
    request = urllib.request.Request("https://example.org/source")
    with pytest.raises(ValueError, match="HTTPS URL"):
        datasets._HTTPSRedirectHandler().redirect_request(request, None, 302, "Found", {}, url)


def test_bundled_inputs_keep_manifest_checksums(tmp_path, monkeypatch):
    monkeypatch.delenv("DRAFT_ASSET_DIR", raising=False)
    monkeypatch.delenv("DRAFT_ASSET_BASE_URL", raising=False)
    bundled = [
        name
        for name, spec in datasets.MANIFEST["files"].items()
        if spec.get("distribution") == "bundled"
    ]
    assert len(bundled) == 10
    for name in bundled:
        assert datasets.asset(name, cache_dir=tmp_path).is_file()
    assert not list(tmp_path.iterdir())


def test_github_publication_is_disabled_before_external_action(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Review publication must not inspect credentials or use the network")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    missing = tmp_path / "no-run"
    with pytest.raises(ValueError, match="publishing is disabled"):
        publish_submission(missing, "owner/repository")
    assert main(["submit", str(missing), "--github"]) == 1
    assert "publishing is disabled" in capsys.readouterr().err
    assert not missing.exists()

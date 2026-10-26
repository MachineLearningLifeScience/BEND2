"""Download and prepare benchmark data.

Small datasets ship with the package; downloaded data use the local cache.
``load(task)`` returns the inputs and provenance for one task.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

MANIFEST = json.loads(Path(__file__).with_name("assets.json").read_text())
FINGERPRINT_VERSION = "bend2-canonical-columns-v1"
_COMMON = (
    ("record_id", "str"),
    ("dataset", "str"),
    ("sequence_ref", "str"),
    ("sequence_alt", "str"),
    ("intervention_type", "str"),
    ("context_id", "str"),
    ("y_ref", "float64"),
    ("y_alt", "float64"),
    ("delta_y", "float64"),
    ("sigma", "float64"),
    ("unit_id", "str"),
)
_IDENTITY = (
    ("locus_id", "str"),
    ("background_id", "str"),
    ("mutation_position", "int64"),
    ("mutation_ref", "str"),
    ("mutation_alt", "str"),
    ("ID", "str"),
)
COLUMNS = {
    "opensplice": _COMMON + (("gene_id", "str"),),
    "siraj": _COMMON + _IDENTITY,
    "context": _COMMON
    + _IDENTITY
    + (
        ("context_delta_y", "float64"),
        ("effect_hepg2", "float64"),
        ("effect_k562", "float64"),
        ("se_hepg2", "float64"),
        ("se_k562", "float64"),
        ("source_record_id_hepg2", "str"),
        ("source_record_id_k562", "str"),
    ),
}
COHORTS = {
    "opensplice": {
        "rows": 590104,
        "groups": 466,
        "group_column": "gene_id",
        "sha256": "158f87ef5570d4255bc42a94ffc5e3310576e2a024ff7d9331f1b6c6b104e59c",
        "basis": "pinned-source-rebuild",
    },
    "siraj": {
        "rows": 340584,
        "groups": 128,
        "group_column": "unit_id",
        "sha256": "e601253785aa4e3a65020c7fde3d259b168df5f9febed97095c124c8cd9cf836",
        "basis": "byte-identical-frozen-cache",
    },
    "context": {
        "rows": 170292,
        "groups": 128,
        "group_column": "unit_id",
        "sha256": "242ea081839d8932fcc0e07adf4f65941e121aa1d17b4bb30dc6f82925772aab",
        "basis": "byte-identical-frozen-cache",
    },
}
_TASK_ASSETS = {
    "prior": {"panel": "prior-panel.parquet"},
    "atlas_profile": {
        "population": "atlas-population.parquet",
        "programs": "atlas-programs.csv",
        "source_activities": "atlas-source-activities.parquet",
        "candidate_activities": "atlas-candidate-activities.parquet",
    },
    "tissue_identification": {
        "targets": "gtex-targets.npz",
        "genes": "gtex-genes.tsv",
        "genome": "hg38.2bit",
    },
}


def task_identity(task):
    """Pinned data used by a task, without downloading or opening the data."""
    if task in _TASK_ASSETS:
        assets, cohorts = list(_TASK_ASSETS[task].values()), []
    elif task == "opensplice":
        assets, cohorts = ["opensplice.tsv.gz"], ["opensplice"]
    else:
        assets = ["siraj.zip", "siraj-numeric-reference.npz"]
        cohorts = ["context"] if task == "context" else ["siraj"]
        if task == "cell_selective":
            assets.append("siraj_selective.parquet")
            cohorts.append("context")
    return {
        "assets": {
            name: {
                key: value
                for key, value in MANIFEST["files"][name].items()
                if key in {"sha256", "md5", "bytes"}
            }
            for name in assets
        },
        "cohorts": {
            name: {
                "semantic_sha256": COHORTS[name]["sha256"],
                "rows": COHORTS[name]["rows"],
                "groups": COHORTS[name]["groups"],
                "fingerprint_version": FINGERPRINT_VERSION,
            }
            for name in cohorts
        },
    }


def cache_root(cache_dir=None) -> Path:
    """Choose the supplied cache path, BEND2_CACHE, or ~/.cache/bend2."""
    if cache_dir is not None:
        return Path(cache_dir).expanduser()
    return Path(os.environ.get("BEND2_CACHE", Path.home() / ".cache" / "bend2")).expanduser()


def _checksum(path, algorithm="sha256") -> str:
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_asset(path: Path, spec: dict) -> None:
    algorithm = "sha256" if "sha256" in spec else "md5"
    if path.stat().st_size != spec["bytes"] or _checksum(path, algorithm) != spec[algorithm]:
        raise ValueError(f"Data checksum mismatch: {path}. Remove this cached file and retry.")


def asset(name: str, cache_dir=None) -> Path:
    """Get a dataset file and verify its checksum.

    Files are loaded from the package, cache, or BEND2_ASSET_DIR mirror before
    downloading. Mirror filenames must match the asset manifest.
    """
    try:
        spec = MANIFEST["files"][name]
    except KeyError:
        raise ValueError(f"Unknown BEND 2.0 data asset: {name}") from None
    algorithm = "sha256" if "sha256" in spec else "md5"
    bundled = Path(__file__).with_name("_data") / name
    if spec.get("distribution") == "bundled":
        _check_asset(bundled, spec)
        return bundled
    destination = cache_root(cache_dir) / "assets" / spec[algorithm] / name
    if destination.exists():
        _check_asset(destination, spec)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    local = os.environ.get("BEND2_ASSET_DIR")
    source = Path(local).expanduser() / name if local else None
    url = spec["url"]
    with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as tmp:
        staged = Path(tmp) / name
        if source is not None and source.exists():
            _check_asset(source, spec)
            shutil.copyfile(source, staged)
        else:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "BEND2/benchmark"})
                with (
                    urllib.request.urlopen(request, timeout=60) as incoming,
                    staged.open("wb") as out,
                ):
                    shutil.copyfileobj(incoming, out, length=8 << 20)
            except (urllib.error.URLError, TimeoutError) as error:
                raise RuntimeError(
                    f"Could not download {name}. Check your connection, or set "
                    "BEND2_ASSET_DIR to an offline source mirror; see docs/data.md."
                ) from error
        _check_asset(staged, spec)
        try:
            os.link(staged, destination)
        except FileExistsError:
            _check_asset(destination, spec)
    return destination


def cohort_fingerprint(name: str, frame: pd.DataFrame) -> str:
    """Hash cohort columns independently of Parquet encoding."""
    if name not in COLUMNS:
        raise ValueError(f"Unknown canonical dataset: {name}")
    schema = COLUMNS[name]
    missing = {key for key, _ in schema} - set(frame.columns)
    if missing or frame.columns.duplicated().any():
        raise ValueError(f"Invalid {name} columns; missing: {sorted(missing)}")
    header = {
        "version": FINGERPRINT_VERSION,
        "task": name,
        "columns": schema,
        "row_order": "preserved",
        "rows": len(frame),
    }
    digest = hashlib.sha256(json.dumps(header, separators=(",", ":")).encode())
    for column, kind in schema:
        values = frame[column]
        if values.isna().any():
            raise ValueError(f"Missing canonical values in {column}")
        if kind == "str":
            for value in values:
                if not isinstance(value, str) or not value:
                    raise ValueError(f"Expected nonempty strings in {column}")
                encoded = value.encode("utf-8")
                digest.update(struct.pack("<Q", len(encoded)))
                digest.update(encoded)
        else:
            if not pd.api.types.is_numeric_dtype(values.dtype):
                raise ValueError(f"Expected numeric values in {column}")
            array = values.to_numpy(dtype="<f8", copy=True)
            if not np.isfinite(array).all():
                raise ValueError(f"Nonfinite canonical values in {column}")
            array[array == 0] = 0.0
            if kind == "int64":
                if not np.equal(array, np.floor(array)).all():
                    raise ValueError(f"Expected integer values in {column}")
                array = array.astype("<i8")
            digest.update(array.tobytes(order="C"))
    if frame.record_id.duplicated().any():
        raise ValueError("Duplicate canonical record IDs")
    for column in ("sequence_ref", "sequence_alt"):
        if not frame[column].str.fullmatch("[ACGTN]+").all():
            raise ValueError(f"Invalid DNA in {column}")
    if (frame.sigma < 0).any():
        raise ValueError("Canonical uncertainty must be nonnegative")
    return digest.hexdigest()


def verify_cohort(name: str, frame: pd.DataFrame) -> dict:
    reference = COHORTS[name]
    observed = cohort_fingerprint(name, frame)
    groups = int(frame[reference["group_column"]].nunique())
    verified = (
        observed == reference["sha256"]
        and len(frame) == reference["rows"]
        and groups == reference["groups"]
    )
    if not verified:
        raise ValueError(f"The {name} data does not match the frozen BEND 2.0 cohort")
    return {
        "semantic_sha256": observed,
        "fingerprint_version": FINGERPRINT_VERSION,
        "rows": len(frame),
        "groups": groups,
        "basis": reference["basis"],
    }


def _dna(sequence) -> str:
    sequence = str(sequence).upper().replace("U", "T")
    if not sequence or set(sequence) - set("ACGTN"):
        raise ValueError("Expected nonempty A/C/G/T/N DNA")
    return sequence


def _opensplice(path: Path) -> pd.DataFrame:
    # These fixed fields and row IDs preserve the published version-5 cohort.
    columns = [
        "nt_seq",
        "ensembl_exon_id",
        "gene",
        "delta_psi",
        "psi",
        "wt_psi",
        "se_psi",
        "start",
        "end",
        "wt",
        "mut_type",
    ]
    raw = pd.read_csv(path, sep="\t", usecols=columns, low_memory=False)
    raw = raw.dropna(subset=["nt_seq", "ensembl_exon_id"]).copy()
    alternate = raw.nt_seq.map(_dna)
    references = []
    for sequence, start, end, wild, kind in zip(
        alternate, raw.start, raw.end, raw.wt, raw.mut_type, strict=True
    ):
        left = int(start) - 1
        right = int(end) if str(kind).lower() == "sub" else left
        references.append(_dna(sequence[:left] + _dna(wild) + sequence[right:]))
    unit = raw.ensembl_exon_id.astype(str)
    frame = pd.DataFrame(
        {
            "record_id": [
                hashlib.sha256(f"opensplice|{u}|{i}".encode()).hexdigest()[:24]
                for i, u in zip(raw.index, unit, strict=True)
            ],
            "dataset": "opensplice",
            "sequence_ref": references,
            "sequence_alt": alternate,
            "intervention_type": raw.mut_type.astype(str),
            "context_id": "minigene_assay",
            "y_ref": pd.to_numeric(raw.wt_psi, errors="coerce"),
            "y_alt": pd.to_numeric(raw.psi, errors="coerce"),
            "delta_y": pd.to_numeric(raw.delta_psi, errors="coerce"),
            "sigma": pd.to_numeric(raw.se_psi, errors="coerce"),
            "unit_id": unit,
            "gene_id": raw.gene.astype(str),
        }
    )
    return frame.dropna(subset=["delta_y"]).reset_index(drop=True)


def _siraj(path: Path, cache_dir=None) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        with archive.open("data/satmut/satmut.txt.gz") as handle:
            raw = pd.read_csv(handle, sep="\t", compression="gzip", low_memory=False)
        with archive.open("data/satmut/satmut_sequences.txt.gz") as handle:
            sequence_table = pd.read_csv(handle, sep="\t", compression="gzip", low_memory=False)
        with archive.open("data/satmut/satmut_final_128elements.txt") as handle:
            elements = pd.read_csv(handle, sep="\t")
    if len(elements) != 128 or elements.sat_ref_parent.duplicated().any():
        raise ValueError("Expected the frozen 128-element Siraj panel")
    raw = raw[raw.sat_ref_parent.isin(elements.sat_ref_parent)].copy()
    if (sequence_table.groupby("final_id").sequence.nunique() > 1).any():
        raise ValueError("Conflicting Siraj sequence IDs")
    sequences = sequence_table.drop_duplicates("final_id").set_index("final_id").sequence.map(_dna)
    raw = raw[raw.oligomut != "m0"].copy()
    contexts = raw.cell_type.replace({"HEPG2": "HepG2"})
    refs = (raw.sat_ref.astype(str) + ":m0").map(sequences)
    alts = raw.ID.map(sequences)
    positions = pd.to_numeric(raw.mut_pos, errors="raise").astype(int) - 1
    ref_bases = [s[p] for s, p in zip(refs, positions, strict=True)]
    delta = pd.to_numeric(raw.post_log2Skew, errors="raise")
    y_alt = pd.to_numeric(raw.post_log2FC, errors="raise")
    frame = pd.DataFrame(
        {
            "record_id": [
                hashlib.sha256(f"siraj_satmut|{i}|{c}".encode()).hexdigest()[:24]
                for i, c in zip(raw.ID, contexts, strict=True)
            ],
            "dataset": "siraj_satmut",
            "sequence_ref": refs,
            "sequence_alt": alts,
            "intervention_type": "regulatory_snv",
            "context_id": contexts,
            "y_ref": y_alt - delta,
            "y_alt": y_alt,
            "delta_y": delta,
            "sigma": pd.to_numeric(raw.log2Skew_SE, errors="coerce"),
            "unit_id": raw.sat_ref_parent.astype(str),
            "locus_id": raw.sat_ref_parent.astype(str),
            "background_id": raw.sat_ref.astype(str),
            "mutation_position": positions,
            "mutation_ref": ref_bases,
            "mutation_alt": raw.mut_base.astype(str).str.upper(),
            "ID": raw.ID,
        }
    ).reset_index(drop=True)
    # CSV parser implementations differ by a few ulps. Restore only pinned-source
    # reconstruction and only after exact ordered-ID and tight numeric checks.
    cohort_fingerprint("siraj", frame)
    with np.load(asset("siraj-numeric-reference.npz", cache_dir), allow_pickle=False) as reference:
        columns = reference["columns"].tolist()
        expected = reference["values"]
        identifiers = np.array([list(bytes.fromhex(v)) for v in frame.record_id], dtype=np.uint8)
        if columns != ["y_ref", "y_alt", "delta_y", "sigma"]:
            raise ValueError("Unexpected frozen numeric-reference columns")
        if not np.array_equal(identifiers, reference["record_id_bytes"]):
            raise ValueError("Siraj record order differs from the frozen release")
        actual = frame[columns].to_numpy(dtype=np.float64)
        if expected.shape != actual.shape or not np.isfinite(expected).all():
            raise ValueError("Invalid frozen numeric reference")
        if np.max(np.abs(actual - expected)) > 2e-14:
            raise ValueError("Siraj source reconstruction differs from frozen measurements")
        frame[columns] = expected
    return frame


def _context(source: pd.DataFrame) -> pd.DataFrame:
    indexed = source.set_index(["ID", "context_id"]).sort_index()
    a = indexed.xs("HepG2", level="context_id").sort_index()
    b = indexed.xs("K562", level="context_id").sort_index()
    if not a.index.equals(b.index):
        raise ValueError("Siraj paired-context identifiers differ")
    columns = [
        "sequence_ref",
        "sequence_alt",
        "unit_id",
        "locus_id",
        "background_id",
        "mutation_position",
        "mutation_ref",
        "mutation_alt",
    ]
    frame = a[columns].copy()
    frame["source_record_id_hepg2"], frame["source_record_id_k562"] = a.record_id, b.record_id
    frame["effect_hepg2"], frame["effect_k562"] = a.delta_y, b.delta_y
    frame["se_hepg2"], frame["se_k562"] = a.sigma, b.sigma
    frame["context_delta_y"] = a.delta_y - b.delta_y
    frame["sigma"] = np.sqrt(a.sigma**2 + b.sigma**2)
    frame["y_ref"], frame["y_alt"] = b.delta_y, a.delta_y
    frame["delta_y"] = frame.context_delta_y
    frame["record_id"] = [
        hashlib.sha256(f"siraj_contextual|{i}|HepG2_minus_K562".encode()).hexdigest()[:24]
        for i in frame.index
    ]
    frame["dataset"] = "siraj_contextual"
    frame["intervention_type"] = "regulatory_context_interaction"
    frame["context_id"] = "HepG2_minus_K562"
    frame["ID"] = frame.index.astype(str)
    return frame.reset_index(drop=True)


def _canonical(name: str, cache_dir=None) -> tuple[Path, dict]:
    path = cache_root(cache_dir) / "prepared" / COHORTS[name]["sha256"] / f"{name}.parquet"
    if path.exists():
        return path, verify_cohort(name, pd.read_parquet(path))
    if name == "opensplice":
        frame = _opensplice(asset("opensplice.tsv.gz", cache_dir))
    elif name == "siraj":
        frame = _siraj(asset("siraj.zip", cache_dir), cache_dir)
    else:
        source, _ = _canonical("siraj", cache_dir)
        frame = _context(pd.read_parquet(source))
    verification = verify_cohort(name, frame)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=path.parent) as directory:
        staged = Path(directory) / path.name
        frame.to_parquet(staged, index=False)
        try:
            os.link(staged, path)
        except FileExistsError:
            verify_cohort(name, pd.read_parquet(path))
    return path, verification


def prepare(task: str, cache_dir=None) -> dict:
    """Prepare one task and return file paths, hashes and source information."""
    paths, cohorts, receipts = {}, {}, {}
    if task in {
        "opensplice",
        "siraj",
        "context",
        "background",
        "repair_percentile",
        "cell_selective",
    }:
        names = (
            ["opensplice"]
            if task == "opensplice"
            else ["context"]
            if task == "context"
            else ["siraj", "context"]
            if task == "cell_selective"
            else ["siraj"]
        )
        for name in names:
            path, verification = _canonical(name, cache_dir)
            key = "context" if name == "context" else "records"
            paths[key], cohorts[name] = str(path), verification
        source_names = (
            ["opensplice.tsv.gz"]
            if task == "opensplice"
            else ["siraj.zip", "siraj-numeric-reference.npz"]
        )
        receipts.update({name: dict(MANIFEST["files"][name]) for name in source_names})
        assets = (
            {"selective_outcomes": "siraj_selective.parquet"} if task == "cell_selective" else {}
        )
    elif task in _TASK_ASSETS:
        assets = _TASK_ASSETS[task]
    else:
        raise ValueError(f"Unknown BEND 2.0 task: {task}")
    for key, name in assets.items():
        paths[key] = str(asset(name, cache_dir))
        receipts[name] = dict(MANIFEST["files"][name])
    sources = {spec["source"]: MANIFEST["sources"][spec["source"]] for spec in receipts.values()}
    return {
        "task": task,
        "paths": paths,
        "cohorts": cohorts,
        "assets": receipts,
        "sources": sources,
    }


class GenomeWindows(Sequence):
    """Read GTEx windows from the 2bit genome on demand."""

    def __init__(self, genome: Path, genes: pd.DataFrame):
        try:
            import py2bit
        except ImportError:
            raise ImportError(
                "GTEx requires py2bit. Install it with: pip install 'bend2[genome]'"
            ) from None
        self._genome = py2bit.open(str(genome))
        self._rows = list(genes[["chrom", "start", "end"]].itertuples(index=False, name=None))

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        chromosome, start, end = self._rows[index]
        sequence = self._genome.sequence(chromosome, int(start), int(end)).upper()
        if len(sequence) != 131072:
            raise ValueError("Unexpected GTEx reference-window length")
        return sequence

    def close(self):
        self._genome.close()


def load(task: str, cache_dir=None) -> dict:
    """Load the inputs for a task.

    GTEx sequences are read on demand; call ``close()`` on the sequence accessor
    when finished. ``_provenance`` records source files and cohort checks.
    """
    if task == "tissue_identification":
        try:
            import py2bit  # noqa: F401
        except ImportError:
            raise ImportError("GTEx requires: pip install 'bend2[genome]'") from None
    metadata = prepare(task, cache_dir)
    result = {"_provenance": metadata}
    for key, value in metadata["paths"].items():
        path = Path(value)
        if path.suffix == ".parquet":
            result[key] = pd.read_parquet(path)
        elif path.suffix in {".csv", ".tsv"}:
            result[key] = pd.read_csv(path, sep="\t" if path.suffix == ".tsv" else ",")
        elif path.suffix == ".npz":
            with np.load(path, allow_pickle=False) as archive:
                result[key] = {name: archive[name] for name in archive.files}
    if task == "tissue_identification":
        genes, targets = result["genes"], result["targets"]
        if not np.array_equal(genes.gene_id.to_numpy(str), targets["gene_ids"]):
            raise ValueError("GTEx sequence and target gene order differs")
        exclusions = set(MANIFEST["gtex_common_test_exclusions"])
        result["test_indices"] = np.array(
            [i for i in targets["test"] if targets["gene_ids"][i] not in exclusions]
        )
        result["required_indices"] = np.sort(
            np.concatenate([targets["train"], targets["validation"], result["test_indices"]])
        )
        result["sequences"] = GenomeWindows(Path(metadata["paths"]["genome"]), genes)
    return result

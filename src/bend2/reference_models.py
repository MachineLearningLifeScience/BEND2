"""Concrete frozen-model readouts with pinned weights, code and preprocessing.

These integrations load optional machine-learning dependencies only on inference.
They download and execute the named checkpoint authors' pinned Python code.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np

from bend2.model import Model

DNABERT2_REPOSITORY = "zhihan1996/DNABERT-2-117M"
DNABERT2_REVISION = "b5d88cda421f106afef78cd286200a5b5b8f6fea"
NTV3_CODE_REVISION = "0ecff3637f0d3ba5b686d1095083218157c2ca34"
PRIOR_QUERY_SEEDS_SHA256 = "7205f435abecec715f8ef23248acbff230bf66b893fb2eb6eb9a591f1f34d3d0"
NTV3_RELEASES = {
    "100m": ("InstaDeepAI/NTv3_100M_post", "b7292f0bd1b5b004d28561783a1890e1ec6f94fd"),
    "650m": ("InstaDeepAI/NTv3_650M_post", "ad622051abbe9376bdea3f2727863fa559957e9f"),
}
_NTV3_MIXED_PRECISION = (
    "stem_compute_dtype",
    "down_convolution_compute_dtype",
    "transformer_qkvo_compute_dtype",
    "transformer_ffn_compute_dtype",
    "up_convolution_compute_dtype",
    "modulation_compute_dtype",
)
_DNABERT2_SOURCES = {
    "bert_padding.py": "44d1c68afb1f585fdc66c150d4c60f1ed44a89c006abc57d50531d71940d7421",
    "bert_layers.py": "317ad7e9667980ac724c07f0174ba265c8446ca5230f6b473068ff1b911edcf9",
}
_TRITON_IMPORT = """try:
    from .flash_attn_triton import flash_attn_qkvpacked_func
except ImportError as e:
    flash_attn_qkvpacked_func = None"""


def _runtime(device, precision):
    if not isinstance(device, str) or not device:
        raise ValueError("device must be a PyTorch device string, such as cpu or cuda:0")
    if precision not in {"float32", "bfloat16"}:
        raise ValueError("Choose precision='float32' or precision='bfloat16'")
    if precision == "bfloat16" and not device.startswith("cuda"):
        raise ValueError("The bfloat16 reference readout requires a compatible CUDA/ROCm GPU")


def _imports():
    try:
        import torch
        import einops  # noqa: F401 — the pinned model source needs it
        from transformers import AutoModel, AutoTokenizer, BertConfig
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "Install the reference runtime: pip install "
            "'bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark'"
        ) from None
    return torch, AutoModel, AutoTokenizer, BertConfig, hf_hub_download


@contextlib.contextmanager
def _precision(torch, device, precision, *, autocast=True):
    # Keep this choice local to inference; restore the caller's numeric settings.
    previous_matmul = torch.backends.cuda.matmul.allow_tf32
    previous_cudnn = torch.backends.cudnn.allow_tf32
    try:
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        if precision == "bfloat16" and not torch.cuda.is_bf16_supported():
            raise ValueError("This GPU does not support the declared bfloat16 readout")
        with (
            torch.inference_mode(),
            torch.autocast(
                device_type=torch.device(device).type,
                dtype=torch.bfloat16,
                enabled=autocast and precision == "bfloat16",
            ),
        ):
            yield
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous_matmul
        torch.backends.cudnn.allow_tf32 = previous_cudnn


def dnabert2(*, device="cpu", precision="float32") -> Model:
    """DNABERT-2 117M: last-layer mean of DNA tokens, 768 unprojected features.

    The weights and PyTorch attention implementation match the paper's frozen
    DNABERT-2 integration. Precision is explicit: the paper's GPU extraction used
    bfloat16 autocast; this portable default uses float32. Inputs longer than 512
    tokens fail instead of being shortened. No nucleotide probabilities are
    inferred from DNABERT-2's variable-length BPE vocabulary.
    """
    _runtime(device, precision)
    encoder = _DNABERT2(device, precision)
    return Model(
        "DNABERT-2 117M",
        embed=encoder,
        revision=DNABERT2_REVISION,
        training_data="Multi-species genome pretraining; released DNABERT-2 117M checkpoint",
        representation=f"Final transformer layer; 768 features; float32 weights; {precision} inference",
        pooling="mean non-special, non-padding tokens; no projection or truncation",
        source=f"https://huggingface.co/{DNABERT2_REPOSITORY}/tree/{DNABERT2_REVISION}",
        unsupported_tasks={
            "tissue_identification": (
                "DNABERT-2 accepts at most 512 tokens; tissue identification requires "
                "131,072 bases without truncation."
            )
        },
        inference_config={
            "adapter": "dnabert2-v1",
            "checkpoint": DNABERT2_REPOSITORY,
            "code_revision": DNABERT2_REVISION,
            "layer": "final",
            "pooling": "mean_non_special_tokens",
            "features": 768,
            "maximum_tokens": 512,
            "precision": precision,
            "device_type": device.split(":", 1)[0],
            "tf32": False,
            "attention": "released PyTorch fallback",
            "compatibility_patch": "disable-optional-triton-import-v1",
            "source_sha256": dict(_DNABERT2_SOURCES),
        },
    )


def ntv3_prior(*, size="100m", readout="paper", device="cpu", precision="float32") -> Model:
    """The paper's two-query NTv3 prior, or its native one-mask alternative.

    The target becomes the released mask token. Logits at that position are
    normalized over A/C/G/T in float64. ``readout='paper'`` additionally hides
    exactly 144 positions using each window's two frozen seeds, and returns
    [batch, 2, 4] for mean individual-query loss. This is not an ensemble.
    ``readout='native'`` returns [batch, 4] with no extra masking.
    """
    if size not in NTV3_RELEASES:
        raise ValueError("Choose size='100m' or size='650m'")
    if readout not in {"paper", "native"}:
        raise ValueError("Choose readout='paper' or readout='native'")
    _runtime(device, precision)
    repository, revision = NTV3_RELEASES[size]
    predictor = _NTv3Prior(repository, revision, readout, device, precision)
    description = (
        "fixed 12% mask; mean individual-query loss across two draws; no ensemble"
        if readout == "paper"
        else "native one-target mask; no additional masking"
    )
    return Model(
        f"NTv3 {size.upper()} post — {readout} prior",
        probabilities=predictor,
        revision=revision,
        training_data=(
            "NTv3 genome pretraining, followed by released multi-species functional-track "
            "and genomic-annotation post-training; see pinned model card"
        ),
        probability_interface=(
            f"human-conditioned MLM; {description}; A/C/G/T-only float64 softmax; "
            f"float32 weights with {precision} inference; no fitted calibration"
        ),
        source=f"https://huggingface.co/{repository}/tree/{revision}",
        inference_config={
            "adapter": "ntv3-prior-v1",
            "readout": readout,
            "checkpoint": repository,
            "code_revision": NTV3_CODE_REVISION,
            "species": "human",
            "target": "mask_token_id",
            "queries": 2 if readout == "paper" else 1,
            "additional_masks": 144 if readout == "paper" else 0,
            "query_seed_table_sha256": PRIOR_QUERY_SEEDS_SHA256 if readout == "paper" else None,
            "mask_policy": "target plus smallest 144 RNG priorities, excluding target and padding"
            if readout == "paper"
            else "target only",
            "query_aggregation": "mean individual-query loss" if readout == "paper" else "none",
            "right_padding": "pad token to multiple of 128",
            "maximum_bases": 1_048_576,
            "normalization": "A/C/G/T float64 softmax",
            "precision": precision,
            "compute_dtypes": {name: precision for name in _NTV3_MIXED_PRECISION},
            "embedding_layernorm_lmhead": "float32",
            "device_type": device.split(":", 1)[0],
            "tf32": False,
            "unused_functional_heads": "disabled; nucleotide logits unchanged",
        },
    )


def _dna(sequences):
    if not sequences or any(
        not isinstance(sequence, str) or not sequence or set(sequence) - set("ACGTN")
        for sequence in sequences
    ):
        raise ValueError("Pass a nonempty batch of uppercase A/C/G/T/N sequences")


def _paper_query_seeds():
    """Only input hashes and random seeds are supplied; no held-out bases or labels."""
    path = Path(__file__).with_name("_data") / "prior-query-seeds.json"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != PRIOR_QUERY_SEEDS_SHA256:
        raise ValueError("The frozen NTv3 query-seed table has changed")
    data = json.loads(content)
    seeds = data["inputs"]
    if data["n_windows"] != 512 or len(seeds) != 512 or data["queries"] != 2:
        raise ValueError("The NTv3 paper readout requires exactly 512 inputs and two seeds each")
    if any(
        len(key) != 64
        or set(key) - set("0123456789abcdef")
        or len(values) != 2
        or any(type(value) is not int or not 0 <= value < 2**64 for value in values)
        for key, values in seeds.items()
    ):
        raise ValueError("Invalid NTv3 input hashes or query seeds")
    return seeds


def _mask_positions(length, target, seed):
    # Identical RNG draw order and sort policy to the frozen Table 1 extraction.
    positions = np.arange(length)
    eligible = positions != target
    priorities = np.random.default_rng(seed).random(length)
    chosen = positions[eligible][np.argsort(priorities[eligible])[:144]]
    return np.r_[target, chosen]


class _DNABERT2:
    def __init__(self, device, precision):
        self.device, self.precision = device, precision
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        torch, _, AutoTokenizer, BertConfig, download = _imports()
        # Transformers recursively checks the optional Triton module before the
        # author's try/except executes. Load the two verified modules with that
        # import disabled. No other source, attention math or weights change.
        package = f"_bend2_dnabert2_{DNABERT2_REVISION}"
        if f"{package}.bert_layers" not in sys.modules:
            namespace = types.ModuleType(package)
            namespace.__path__ = []
            sys.modules[package] = namespace
            for filename, expected in _DNABERT2_SOURCES.items():
                path = Path(download(DNABERT2_REPOSITORY, filename, revision=DNABERT2_REVISION))
                source = path.read_bytes()
                if hashlib.sha256(source).hexdigest() != expected:
                    raise ValueError(f"Pinned DNABERT-2 source checksum differs: {filename}")
                source = source.decode()
                if filename == "bert_layers.py":
                    if source.count(_TRITON_IMPORT) != 1:
                        raise ValueError("Pinned DNABERT-2 optional import has changed")
                    source = source.replace(_TRITON_IMPORT, "flash_attn_qkvpacked_func = None")
                name = f"{package}.{Path(filename).stem}"
                module = types.ModuleType(name)
                module.__file__, module.__package__ = str(path), package
                sys.modules[name] = module
                exec(compile(source, str(path), "exec"), module.__dict__)
        options = dict(revision=DNABERT2_REVISION)
        config = BertConfig.from_pretrained(DNABERT2_REPOSITORY, **options)
        self._tokenizer = AutoTokenizer.from_pretrained(DNABERT2_REPOSITORY, **options)
        model_class = sys.modules[f"{package}.bert_layers"].BertModel
        model, loading = model_class.from_pretrained(
            DNABERT2_REPOSITORY,
            config=config,
            add_pooling_layer=False,
            use_safetensors=True,
            dtype=torch.float32,
            output_loading_info=True,
            **options,
        )
        if any(loading.get(key) for key in ("missing_keys", "mismatched_keys", "error_msgs")):
            raise ValueError(f"Incomplete DNABERT-2 weight loading: {loading}")
        if any(not key.startswith("cls.") for key in loading.get("unexpected_keys", [])):
            raise ValueError(f"Unexpected DNABERT-2 checkpoint weights: {loading}")
        self._model = model.to(self.device).eval().requires_grad_(False)
        if self._model.config.hidden_size != 768:
            raise ValueError("The pinned DNABERT-2 checkpoint must produce 768 features")

    def __call__(self, sequences):
        _dna(sequences)
        self._load()
        import torch

        tokens = self._tokenizer(
            sequences,
            padding=True,
            truncation=False,
            return_special_tokens_mask=True,
            return_tensors="pt",
        )
        if tokens["input_ids"].shape[1] > 512:
            raise ValueError(
                "DNABERT-2's reference readout accepts at most 512 tokens. "
                "Choose a longer-context model for this task; sequences are never truncated."
            )
        keep = tokens.pop("special_tokens_mask").bool().logical_not()
        keep &= tokens["attention_mask"].bool()
        for token_id in self._tokenizer.all_special_ids:
            keep &= tokens["input_ids"] != token_id
        if (keep.sum(1) == 0).any():
            raise ValueError("DNABERT-2 tokenization produced no DNA tokens to pool")
        tokens = {key: value.to(self.device) for key, value in tokens.items()}
        keep = keep.to(self.device)
        with _precision(torch, self.device, self.precision):
            hidden = self._model(**tokens)[0]
            if hidden.shape != (*tokens["input_ids"].shape, 768):
                raise ValueError("Unexpected DNABERT-2 final-layer shape")
            values = (hidden.float() * keep.unsqueeze(-1)).sum(1) / keep.sum(1, keepdim=True)
        return values.cpu().numpy().astype(np.float32, copy=False)


class _NTv3Prior:
    def __init__(self, repository, revision, readout, device, precision):
        self.repository, self.revision = repository, revision
        self.readout = readout
        self.device, self.precision = device, precision
        self._seeds = _paper_query_seeds() if readout == "paper" else None
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        torch, AutoModel, AutoTokenizer, _, _ = _imports()
        options = dict(
            revision=self.revision, code_revision=NTV3_CODE_REVISION, trust_remote_code=True
        )
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.repository, **options)
            model, loading = AutoModel.from_pretrained(
                self.repository,
                use_safetensors=True,
                dtype=torch.float32,
                output_loading_info=True,
                **{name: self.precision for name in _NTV3_MIXED_PRECISION},
                **options,
            )
            if any(
                loading.get(key)
                for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
            ):
                raise ValueError(f"Incomplete NTv3 weight loading: {loading}")
            # These heads consume the decoder output after its MLM logits have
            # been computed, and do not feed back into the nucleotide predictor.
            # Avoid allocating every species' unused functional-track outputs.
            model.core.bigwig_head = None
            model.core.bed_head = None
            self._model = model.to(self.device).eval().requires_grad_(False)
        except OSError as error:
            raise RuntimeError(
                f"Could not load pinned {self.repository}. The released checkpoint requires "
                "Hugging Face access: accept its model terms and authenticate with hf auth login. "
                "The original download error is attached."
            ) from error
        self._base_ids = self._tokenizer.convert_tokens_to_ids(list("ACGT"))
        if len(set(self._base_ids)) != 4 or self._tokenizer.unk_token_id in self._base_ids:
            raise ValueError("NTv3 must expose one distinct vocabulary token per A/C/G/T base")

    def __call__(self, sequences, positions):
        _dna(sequences)
        if len(positions) != len(sequences):
            raise ValueError("Supply one hidden target position per sequence")
        if any(
            not isinstance(position, (int, np.integer))
            or not 0 <= position < len(sequence)
            or sequence[position] != "N"
            for sequence, position in zip(sequences, positions, strict=True)
        ):
            raise ValueError("Each zero-based target must already be hidden with N")
        if max(map(len, sequences)) > 1_048_576:
            raise ValueError("NTv3 inputs cannot exceed 1,048,576 bases; no truncation is applied")
        seeds = []
        if self.readout == "paper":
            for sequence, position in zip(sequences, positions, strict=True):
                key = hashlib.sha256(f"{position}:{sequence}".encode("ascii")).hexdigest()
                if len(sequence) != 1200 or position != 600 or key not in self._seeds:
                    raise ValueError(
                        "The paper readout's fixed queries cover the 512 benchmark prior windows. "
                        "Use readout='native' for other inputs; no replacement seeds are invented."
                    )
                seeds.append(self._seeds[key])
        self._load()
        import torch

        tokens = self._tokenizer(
            sequences,
            add_special_tokens=False,
            padding=True,
            pad_to_multiple_of=128,
            truncation=False,
            return_tensors="pt",
        )
        # Assert positional correspondence rather than assuming a tokenizer's geometry.
        for row, sequence in zip(tokens["input_ids"], sequences, strict=True):
            expected = self._tokenizer.convert_tokens_to_ids(list(sequence))
            if row[: len(sequence)].tolist() != expected:
                raise ValueError("NTv3 tokenization changed the input's nucleotide coordinates")
        batch_index = torch.arange(len(sequences))
        queries = []
        for draw in range(2 if self.readout == "paper" else 1):
            ids = tokens["input_ids"].clone()
            for index, (sequence, position) in enumerate(zip(sequences, positions, strict=True)):
                masked = (
                    _mask_positions(len(sequence), position, seeds[index][draw])
                    if seeds
                    else [position]
                )
                ids[index, masked] = self._tokenizer.mask_token_id
            inputs = {key: value.to(self.device) for key, value in tokens.items()}
            inputs["input_ids"] = ids.to(self.device)
            inputs["species_ids"] = self._model.encode_species(["human"] * len(sequences)).to(
                self.device
            )
            # The released model controls autocast separately for each block.
            with _precision(torch, self.device, self.precision, autocast=False):
                logits = self._model(**inputs, output_track=False).logits
                selected = (
                    logits[
                        batch_index.to(self.device), torch.tensor(positions, device=self.device)
                    ][:, self._base_ids]
                    .float()
                    .cpu()
                    .numpy()
                    .astype(np.float64)
                )
            selected -= selected.max(axis=1, keepdims=True)
            probabilities = np.exp(selected)
            queries.append(probabilities / probabilities.sum(axis=1, keepdims=True))
        return np.stack(queries, axis=1) if self.readout == "paper" else queries[0]

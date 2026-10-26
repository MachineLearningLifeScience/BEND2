# Data, downloads, and attribution

BEND 2.0 includes the small frozen panels needed to reproduce its task definitions.
Large public source files download when a selected task first needs them. Model
weights are separate and depend on your adapter.

| Tasks | Included data | First additional download |
|---|---|---|
| Sequence priors | 1,536 reference windows: 1,024 baseline-training and 512 evaluation | None |
| Atlas profile control | Frozen source/candidate split and two measured replicates across 12 cell types | None |
| Regulatory context, background sensitivity, repair, cell-selective design | Exact numeric reference and pooled-count design outcomes | Siraj release: 93.3 MB |
| OpenSplice | Dataset manifest | OpenSplice version 5: 425.5 MB |
| Tissue identification | 19,282 genes, 51 tissue targets, and frozen splits | hg38 reference genome: 835.4 MB |

The nine bundled files total 31.1 MB before wheel compression. They contain
reference sequences, measured targets, and split definitions. They contain no
model weights, research run directories, or archived model predictions.

## Cache and offline use

The default cache is `~/.cache/bend2`. Pass `cache_dir="/scratch/bend2"` in Python
or set `BEND2_CACHE` to choose another location. Large sources are stored under
their content digest; canonical tables use a digest of their scientific columns.
Repeated runs reuse these files. A checksum mismatch stops the run rather than
silently replacing modified input.

For a machine without internet access, predownload the following files into one
directory and set `BEND2_ASSET_DIR` to that directory:

| Local filename | Upstream source |
|---|---|
| `opensplice.tsv.gz` | [OpenSplice version 5 experimental master table](https://ndownloader.figshare.com/files/64886694) |
| `siraj.zip` | [Siraj saturation-mutagenesis archive](https://zenodo.org/api/records/15297965/files/data_satmut.zip/content) |
| `hg38.2bit` | [UCSC hg38 reference genome](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.2bit) |

Only the files needed by your chosen tasks are required. Offline inputs undergo
the same size and checksum verification as downloads. You can also populate a
cache on one machine and copy it to another. Install `bend2[genome]` to read the
GTEx reference windows. These windows are read on demand from the 2bit genome;
BEND does not create a second 2.5 GB sequence file.

### Inference and readout storage

Embedding and prior caches are separate from datasets. Each successful inference
batch is committed, so reducing batch size after an interruption retains the work.
Cache keys bind weights, adapter code and declared numerical configuration, without
binding display metadata or command-line code. Prior values preserve float64
probabilities and individual-query shapes. Both caches check stored byte hashes.

Wide intervention readouts write alternate-minus-reference features once to
`<cache>/readouts/` and access bounded windows while fitting. Temporary files are
removed on success or ordinary failure; an operating-system kill may leave a
`bend2-*` scratch directory that can be deleted once no evaluation is using it.
Budget roughly `4 × number_of_records × embedding_width` bytes for this scratch
matrix, in addition to the reusable embedding database. For OpenSplice at 4,096
features that is about 9.7 GB. Use fast local scratch on a cluster when available.
The small-feature path retains the original scikit-learn fit; both paths use the
same groups, features, regularization and solver tolerance.

## Sources and terms

The software license does not replace the terms of the underlying data.
The machine-readable [asset manifest](../src/bend2/assets.json) records exact
sizes, checksums, source identifiers, and the origin of each derived panel.

**OpenSplice:** [Figshare version 5](https://doi.org/10.6084/m9.figshare.32337414.v5),
CC BY 4.0. The pinned 425,453,242-byte master table has MD5
`374443aa36bc1070dfd36318d8e77c59`. Preparation retains 590,104 interventions in
466 genes. Its scientific-column fingerprint was reproduced from the pinned
source across two pandas/Arrow environments; this is a source rebuild, not a
claim that Parquet bytes match the original research cache.

**Siraj saturation mutagenesis:** Siraj et al., *Functional dissection of complex
and molecular trait variants at single nucleotide resolution*,
[Zenodo 15297965](https://doi.org/10.5281/zenodo.15297965), CC BY-NC 4.0.
The 93,320,206-byte source ZIP has MD5 `0043848d7658ac5cf402634b9685102e`.
Preparation preserves 340,584 mutation/cell records across 128 elements; pairing
HepG2 minus K562 produces 170,292 context records.

The bundled Siraj numeric reference contains original float64 measurements and
ordered record IDs. CSV parsers can differ by a few ulps. After verifying the
raw ZIP, preparation requires exact record IDs and reconstructed numeric values
within `2e-14`, restores the frozen values, then verifies every scientific column
including sequences. This tolerance applies only to reconstructing the pinned
source; arbitrary supplied data is never accepted through a tolerant comparison.

Cell-selective design uses the separate pooled-count outcomes, not the release's
posterior mutation effects. The compact table preserves 181,458 identifiers and
two measured effects. Counts originate from ENCODE
[ENCFF769XOF](https://www.encodeproject.org/files/ENCFF769XOF/) and
[ENCFF526SMM](https://www.encodeproject.org/files/ENCFF526SMM/).
Each effect averages `log2((RNA + 0.5)/(DNA + 0.5))` across five repeats and
subtracts the explicit parental no-edit construct. Bundling this result avoids
an 8.95 GB download. Retain Siraj attribution and noncommercial terms for this
combined derived table, and acknowledge the ENCODE Consortium, producers, and
accessions according to its [data-use policy](https://www.encodeproject.org/help/citing-encode/).

**Atlas of AI-designed enhancers:** Castillo-Hair et al., *Programming human
cell type-specific gene expression via an atlas of AI-designed enhancers*,
[Zenodo 17410822](https://doi.org/10.5281/zenodo.17410822), CC BY 4.0.
The frozen population has 7,684 rows: 5,246 eligible source constructs, 2,411
candidates, and 27 excluded source constructs whose families touch candidates.
Activity tables retain the two original float64 normalized replicates in 12 cell
types. Normalization uses matched DNA, a pseudocount of 0.5, and the median of
the 35 published negative controls. Source and candidate measurements are stored
separately so readout fitting does not consume candidate outcomes.

**Human reference panels:** The prior panel contains 1,536 fixed-strand,
1,200-base windows from [UCSC GRCh38/hg38](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/README.txt).
Its 512 evaluation windows occupy genomic blocks excluded from earlier prior
panels; this does not imply those sequences were unseen in model pretraining.
The genome download is the frozen 835,393,456-byte `hg38.2bit`, SHA-256
`1f67aaa17a77b327738fe750ab37430a85dddf73c7d9189385ad1839259acec0`.
Reference assembly attribution and upstream terms apply; no new license is
assigned to the human reference sequence by this package.

**GTEx tissue identification:** Targets are `log1p(TPM)` from the public
[GTEx v10 median expression summary](https://gtexportal.org/home/datasets), joined
to GTEx's GENCODE v39 gene model. Only public aggregate expression is included;
there is no individual-level genotype or donor data. Cite GTEx and follow its
current public-data usage guidance. The frozen cohort contains 12,146 training,
1,350 validation, and 5,786 held-out genes. Four held-out genes lacking complete
native/reference predictions in the paper remain excluded, leaving the same
5,782-gene evaluation cohort. Each sequence is a 131,072-base window centered on
the 1-based TSS, read in reference-forward orientation without strand reversal.

## What is frozen

Asset byte hashes and canonical scientific-column hashes prevent a new library
version, upstream re-upload, or different Parquet encoding from silently changing
the benchmark. Canonical hashes preserve row order, string identity, and exact
float64 values while ignoring Parquet compression, extra columns, and dataframe
indices. Task outputs record these data identities alongside the model identity.
The source preparation and readout protocols derive from the paper's preserved
review snapshot; this implementation keeps their scientific content and leaves
that review branch unchanged.

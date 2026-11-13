# Data, downloads, and attribution

DRAFT includes the smaller datasets. Larger source files retain their original
sizes and checksums in [the asset manifest](../src/draft/assets.json).
Missing larger files are downloaded from the original Figshare, Zenodo or UCSC
source and checked against those pinned values. Your model adapter loads model
weights separately.

## Cache and offline use

The default cache is `~/.cache/draft`. Use `--cache-dir /scratch/draft`,
`cache_dir="/scratch/draft"` in Python, or `DRAFT_CACHE` to choose another location.

To use existing files without downloading them, place them in a directory and set:

```bash
export DRAFT_ASSET_DIR=/path/to/data
```

| Local filename | Original source |
|---|---|
| `opensplice.tsv.gz` | OpenSplice version 5 experimental master table |
| `siraj.zip` | Siraj saturation-mutagenesis archive |
| `hg38.2bit` | UCSC hg38 reference genome |

An optional `DRAFT_ASSET_BASE_URL` can point to an explicitly chosen HTTPS mirror
with those exact filenames. Otherwise the official upstream URLs in the manifest
are used.

Only files required by the selected tasks are downloaded. Their hashes are
checked before use; do not substitute another dataset version. See the original
sources below for attribution. Downloads use the dataset publishers directly,
without a project-specific public account.

For wide embeddings, fitting readouts needs temporary disk space under
`<cache>/readouts/`: approximately `4 × records × embedding_width` bytes.
Keep the inference cache to resume interrupted runs.

## Sources and terms

The software license does not replace the terms of the underlying data.
The [asset manifest](../src/draft/assets.json) records sizes, checksums, source
identifiers and the origin of each derived dataset.

**OpenSplice:** [Figshare version 5](https://doi.org/10.6084/m9.figshare.32337414.v5),
CC BY 4.0. Preparation retains 590,104 interventions in 466 genes.

**Siraj saturation mutagenesis:** Siraj et al., *Functional dissection of complex
and molecular trait variants at single nucleotide resolution*,
[Zenodo 15297965](https://doi.org/10.5281/zenodo.15297965), CC BY-NC 4.0.
Preparation preserves 340,584 mutation/cell records across 128 elements; pairing
HepG2 minus K562 produces 170,292 context records.

Cell-selective design uses the separate pooled-count outcomes, not the release's
posterior mutation effects. The compact table preserves 181,458 identifiers and
two measured effects. Counts originate from ENCODE
[ENCFF769XOF](https://www.encodeproject.org/files/ENCFF769XOF/) and
[ENCFF526SMM](https://www.encodeproject.org/files/ENCFF526SMM/).
Each effect averages `log2((RNA + 0.5)/(DNA + 0.5))` across five repeats and
subtracts the parental no-edit construct. Retain Siraj attribution and
noncommercial terms for this combined derived table, and acknowledge the ENCODE Consortium, producers, and
accessions according to its [data-use policy](https://www.encodeproject.org/help/citing-encode/).

**Atlas of AI-designed enhancers:** Castillo-Hair et al., *Programming human
cell type-specific gene expression via an atlas of AI-designed enhancers*,
[Zenodo 17410822](https://doi.org/10.5281/zenodo.17410822), CC BY 4.0.
The population has 7,684 rows: 5,246 eligible source constructs, 2,411
candidates, and 27 excluded source constructs whose families touch candidates.
Activity tables retain the two original float64 normalized replicates in 12 cell
types. Normalization uses matched DNA, a pseudocount of 0.5, and the median of
the 35 published negative controls. Source and candidate measurements are stored
separately so readout fitting does not consume candidate outcomes.

**Human reference panels:** The prior panel contains 1,536 fixed-strand,
1,200-base windows from [UCSC GRCh38/hg38](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/README.txt).
Its 512 evaluation windows occupy genomic blocks excluded from earlier prior
panels; this does not imply those sequences were unseen in model pretraining.
Reference assembly attribution and upstream terms apply.

The NTv3 paper-prior adapter includes query seeds for the 512 masked inputs,
matching the two-query procedure in Table 1. See the
[adapter description](models.md#ntv3-prior) for how this differs from single-mask
prediction. The seed table excludes sequences, target bases and outcomes.

**GTEx tissue identification:** Targets are `log1p(TPM)` from the public
[GTEx v10 median expression summary](https://gtexportal.org/home/datasets), joined
to GTEx's GENCODE v39 gene model. Only public aggregate expression is included;
there is no individual-level genotype or donor data. Cite GTEx and follow its
current public-data usage guidance. The frozen cohort contains 12,146 training,
1,350 validation, and 5,786 held-out genes. Four held-out genes lacking complete
native/reference predictions in the paper remain excluded, leaving the same
5,782-gene evaluation cohort. Each sequence is a 131,072-base window centered on
the 1-based TSS, read in reference-forward orientation without strand reversal.

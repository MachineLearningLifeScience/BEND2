# Data, downloads, and attribution

BEND 2.0 includes the smaller datasets and downloads larger files from the
[BEND 2.0 release on Hugging Face](https://huggingface.co/datasets/yhsure/BEND2)
when needed. Downloads use the fixed data revision
`0c1dda471ad13c6126c2cd00cb3fa34852e70673`, with the original filenames, sizes
and checksums. The mirror contains unchanged source files; the original hosts
are retained in the manifest for attribution and are not needed for downloads.
Your adapter loads or downloads model weights separately.

## Cache and offline use

The default cache is `~/.cache/bend2`. Use `--cache-dir /scratch/bend2`,
`cache_dir="/scratch/bend2"` in Python, or `BEND2_CACHE` to choose another location.
Keep inference caches to resume interrupted runs; scores and prediction tables
are saved separately in the result directory.

For a machine without internet access, predownload the following files into one
directory and set `BEND2_ASSET_DIR` to that directory:

| Local filename | Frozen download |
|---|---|
| `opensplice.tsv.gz` | [OpenSplice version 5 experimental master table](https://huggingface.co/datasets/yhsure/BEND2/resolve/0c1dda471ad13c6126c2cd00cb3fa34852e70673/data/opensplice.tsv.gz) |
| `siraj.zip` | [Siraj saturation-mutagenesis archive](https://huggingface.co/datasets/yhsure/BEND2/resolve/0c1dda471ad13c6126c2cd00cb3fa34852e70673/data/siraj.zip) |
| `hg38.2bit` | [UCSC hg38 reference genome](https://huggingface.co/datasets/yhsure/BEND2/resolve/0c1dda471ad13c6126c2cd00cb3fa34852e70673/data/hg38.2bit) |

Only the files needed by your tasks are required. Offline files are verified
like downloads. You can also populate a cache on one machine and copy it to another.

With the [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli),
you can fetch all three files in one command:

```bash
hf download yhsure/BEND2 data/opensplice.tsv.gz data/siraj.zip data/hg38.2bit \
  --repo-type dataset --revision 0c1dda471ad13c6126c2cd00cb3fa34852e70673 \
  --local-dir bend2-data
export BEND2_ASSET_DIR="$PWD/bend2-data/data"
```

Omit filenames for tasks you will not run. `BEND2_ASSET_DIR` points directly to
the directory containing those files; it does not replace the small datasets
bundled with the package. A missing file is downloaded when its task runs.

Changing the download host does not change the benchmark data or invalidate
existing verified caches and compatible runs.

For wide embeddings, readout fitting needs temporary disk space under
`<cache>/readouts/`: roughly `4 × number_of_records × embedding_width` bytes,
about 9.7 GB for OpenSplice at 4,096 features, in addition to the embedding cache.
Use fast local scratch when available. After a forced process kill, unused
`bend2-*` directories in that folder can be deleted.

## Sources and terms

The software license does not replace the terms of the underlying data.
The [asset manifest](../src/bend2/assets.json) records sizes, checksums, source
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

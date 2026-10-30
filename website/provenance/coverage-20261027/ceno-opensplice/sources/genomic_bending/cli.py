from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from genomic_bending.data.compass import prepare_compass
from genomic_bending.data.download import download_source, load_manifest
from genomic_bending.data.encode_mpra import prepare_encode_mpra_context
from genomic_bending.data.froemel import prepare_froemel
from genomic_bending.data.georgakopoulos import prepare_georgakopoulos
from genomic_bending.data.gosai import prepare_gosai_coda, prepare_gosai_training
from genomic_bending.data.kircher import prepare_kircher_satmut
from genomic_bending.data.opensplice import prepare_opensplice
from genomic_bending.data.re2g import prepare_re2g
from genomic_bending.data.siraj import prepare_siraj, prepare_siraj_contextual
from genomic_bending.eval.bootstrap import group_bootstrap_ci
from genomic_bending.eval.metrics import evaluate_predictions
from genomic_bending.eval.replicates import estimate_replicate_ceiling
from genomic_bending.models.embeddings import (
    EmbeddingContextRidge,
    InterventionEmbeddingRidge,
    load_embedding_archive,
)
from genomic_bending.models.kmer import KmerContextRidge
from genomic_bending.splits.group import assign_group_splits


def _read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def _write_json(path: str | Path, payload: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _embedding_metadata(path: str | Path) -> dict:
    sidecar = Path(path).with_suffix(".json")
    return json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genomic-bending")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sources = subparsers.add_parser("sources")
    sources.add_argument("manifest")
    download = subparsers.add_parser("download")
    download.add_argument("manifest")
    download.add_argument("source")
    download.add_argument("--raw-root", default="data/raw")
    froemel = subparsers.add_parser("prepare-froemel")
    froemel.add_argument("input")
    froemel.add_argument("output")
    encode_mpra = subparsers.add_parser("prepare-encode-mpra-context")
    encode_mpra.add_argument("design")
    encode_mpra.add_argument("scores")
    encode_mpra.add_argument("output")
    encode_mpra.add_argument("--locus-gap", type=int, default=10_000)
    georgakopoulos = subparsers.add_parser("prepare-georgakopoulos")
    georgakopoulos.add_argument("design")
    georgakopoulos.add_argument("replicates", nargs=3)
    georgakopoulos.add_argument("output")
    georgakopoulos.add_argument("--min-tags", type=int, default=3)
    georgakopoulos.add_argument("--min-replicates", type=int, default=2)
    gosai_training = subparsers.add_parser("prepare-gosai-training")
    gosai_training.add_argument("input")
    gosai_training.add_argument("output")
    gosai_coda = subparsers.add_parser("prepare-gosai-coda")
    gosai_coda.add_argument("input")
    gosai_coda.add_argument("output")
    opensplice = subparsers.add_parser("prepare-opensplice")
    opensplice.add_argument("input")
    opensplice.add_argument("output")
    re2g = subparsers.add_parser("prepare-re2g")
    re2g.add_argument("training")
    re2g.add_argument("heldout")
    re2g.add_argument("output")
    compass = subparsers.add_parser("prepare-compass")
    compass.add_argument("input")
    compass.add_argument("output")
    siraj = subparsers.add_parser("prepare-siraj")
    siraj.add_argument("results")
    siraj.add_argument("sequences")
    siraj.add_argument("elements")
    siraj.add_argument("output")
    siraj_context = subparsers.add_parser("prepare-siraj-context")
    siraj_context.add_argument("input")
    siraj_context.add_argument("output")
    kircher = subparsers.add_parser("prepare-kircher-satmut")
    kircher.add_argument("input_directory")
    kircher.add_argument("output")
    kircher.add_argument("--min-tags", type=int, default=10)
    split = subparsers.add_parser("split")
    split.add_argument("input")
    split.add_argument("output")
    split.add_argument("--group-column", default="unit_id")
    split.add_argument("--seed", type=int, default=20260822)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("input")
    baseline.add_argument("output")
    baseline.add_argument("--target", default="y_alt")
    baseline.add_argument("--alpha", type=float, default=10.0)
    baseline.add_argument("--k-min", type=int, default=3)
    baseline.add_argument("--k-max", type=int, default=6)
    native = subparsers.add_parser("native-scores")
    native.add_argument("input")
    native.add_argument("output")
    native.add_argument("--target", default="delta_y")
    native.add_argument("--group-column", default="unit_id")
    native.add_argument("--split", default="test")
    calibrated = subparsers.add_parser("calibrate-native")
    calibrated.add_argument("input")
    calibrated.add_argument("output")
    calibrated.add_argument("--target", default="delta_y")
    calibrated.add_argument("--group-column", default="unit_id")
    crossval = subparsers.add_parser("crossval-baseline")
    crossval.add_argument("input")
    crossval.add_argument("output")
    crossval.add_argument("--target", default="y_alt")
    crossval.add_argument("--group-column", default="unit_id")
    crossval.add_argument("--folds", type=int, default=5)
    crossval.add_argument("--alpha", type=float, default=10.0)
    crossval.add_argument("--k-min", type=int, default=3)
    crossval.add_argument("--k-max", type=int, default=6)
    ceiling = subparsers.add_parser("assay-ceiling")
    ceiling.add_argument("input")
    ceiling.add_argument("output")
    ceiling.add_argument("--replicates", nargs="+", required=True)
    ceiling.add_argument("--group-column", default="unit_id")
    ceiling.add_argument("--split", default="all")
    embedding_cv = subparsers.add_parser("crossval-embeddings")
    embedding_cv.add_argument("input")
    embedding_cv.add_argument("embeddings")
    embedding_cv.add_argument("output")
    embedding_cv.add_argument("--target", default="y_alt")
    embedding_cv.add_argument("--group-column", default="unit_id")
    embedding_cv.add_argument("--folds", type=int, default=5)
    embedding_cv.add_argument("--alpha", type=float, default=10.0)
    intervention_cv = subparsers.add_parser("crossval-intervention-embeddings")
    intervention_cv.add_argument("input")
    intervention_cv.add_argument("embeddings")
    intervention_cv.add_argument("output")
    intervention_cv.add_argument("--target", default="delta_y")
    intervention_cv.add_argument("--group-column", default="gene_id")
    intervention_cv.add_argument("--folds", type=int, default=5)
    intervention_cv.add_argument("--alpha", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "sources":
        for name, source in load_manifest(args.manifest).items():
            print(f"{name}\t{source['version']}\t{source['license']}\t{source.get('doi', '—')}")
    elif args.command == "download":
        print(download_source(args.manifest, args.source, args.raw_root))
    elif args.command == "prepare-froemel":
        frame = prepare_froemel(args.input, args.output)
        print(f"wrote {len(frame):,} records to {args.output}")
    elif args.command == "prepare-encode-mpra-context":
        frame = prepare_encode_mpra_context(
            args.design, args.scores, args.output, locus_gap=args.locus_gap
        )
        print(
            f"wrote {len(frame):,} records from {frame['element_id'].nunique():,} "
            f"elements and {frame['split_group'].nunique():,} hardened split groups "
            f"to {args.output}"
        )
    elif args.command == "prepare-georgakopoulos":
        frame = prepare_georgakopoulos(
            args.design,
            args.replicates,
            args.output,
            min_tags=args.min_tags,
            min_replicates=args.min_replicates,
        )
        counts = frame.groupby("complexity").size().to_dict()
        print(f"wrote {len(frame):,} clean TFBS grammar records to {args.output}: {counts}")
    elif args.command == "prepare-gosai-training":
        frame = prepare_gosai_training(args.input, args.output)
        counts = frame.groupby("split").size().to_dict()
        print(f"wrote {len(frame):,} Gosai training records to {args.output}: {counts}")
    elif args.command == "prepare-gosai-coda":
        frame = prepare_gosai_coda(args.input, args.output)
        print(
            f"wrote {len(frame):,} CODA records to {args.output}; "
            f"quality={frame['quality_pass'].sum():,}, "
            f"headline={frame['headline_eligible'].sum():,}"
        )
    elif args.command == "prepare-opensplice":
        frame = prepare_opensplice(args.input, args.output)
        print(f"wrote {len(frame):,} records to {args.output}")
    elif args.command == "prepare-re2g":
        frame = prepare_re2g(args.training, args.heldout, args.output)
        print(f"wrote {len(frame):,} records to {args.output}")
    elif args.command == "prepare-compass":
        frame = prepare_compass(args.input, args.output)
        print(f"wrote {len(frame):,} complete quartet-context records to {args.output}")
    elif args.command == "prepare-siraj":
        frame = prepare_siraj(args.results, args.sequences, args.elements, args.output)
        print(
            f"wrote {len(frame):,} records from {frame['unit_id'].nunique()} elements "
            f"and {frame['context_id'].nunique()} contexts to {args.output}"
        )
    elif args.command == "prepare-siraj-context":
        frame = prepare_siraj_contextual(args.input, args.output)
        print(
            f"wrote {len(frame):,} paired mutations from {frame['unit_id'].nunique()} "
            f"elements to {args.output}"
        )
    elif args.command == "prepare-kircher-satmut":
        frame = prepare_kircher_satmut(
            args.input_directory,
            args.output,
            min_tags=args.min_tags,
            validate_release_counts=args.min_tags == 10,
        )
        counts = frame["intervention_type"].value_counts().to_dict()
        print(
            f"wrote {len(frame):,} records from {frame['unit_id'].nunique()} regulatory "
            f"elements to {args.output}: {counts}"
        )
    elif args.command == "split":
        frame = assign_group_splits(_read_table(args.input), args.group_column, seed=args.seed)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.output, index=False)
        summary = frame.groupby("split").agg(
            records=("record_id", "size"), groups=(args.group_column, "nunique")
        )
        print(summary.to_string())
    elif args.command == "baseline":
        frame = _read_table(args.input)
        train = frame[frame["split"] == "train"]
        test = frame[frame["split"] == "test"].copy()
        model = KmerContextRidge(k_min=args.k_min, k_max=args.k_max, alpha=args.alpha)
        model.fit(train, target=args.target)
        test["y_true"] = test[args.target]
        test["y_pred"] = model.predict(test)
        metrics, per_group = evaluate_predictions(test)
        for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy", "ndcg"):
            low, high = group_bootstrap_ci(per_group, metric)
            metrics[f"macro_{metric}_ci95"] = [low, high]
        _write_json(args.output, metrics)
        prediction_path = Path(args.output).with_suffix(".predictions.parquet")
        test[["record_id", "unit_id", "context_id", "y_true", "y_pred"]].to_parquet(
            prediction_path, index=False
        )
        print(json.dumps(metrics, indent=2, sort_keys=True))
    elif args.command == "native-scores":
        frame = _read_table(args.input)
        if "split" in frame and args.split != "all":
            frame = frame[frame["split"] == args.split]
        score_columns = sorted(name for name in frame if name.startswith("score_"))
        if not score_columns:
            raise ValueError("No score_* columns found")
        report = {}
        for score in score_columns:
            evaluation = frame[[args.group_column, args.target, score]].rename(
                columns={args.target: "y_true", score: "y_pred"}
            )
            metrics, per_group = evaluate_predictions(evaluation, group_column=args.group_column)
            for metric in (
                "spearman",
                "pearson",
                "rmse",
                "mae",
                "direction_accuracy",
                "ndcg",
            ):
                low, high = group_bootstrap_ci(per_group, metric)
                metrics[f"macro_{metric}_ci95"] = [low, high]
            report[score.removeprefix("score_")] = metrics
        _write_json(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "calibrate-native":
        frame = _read_table(args.input)
        validation = frame[frame["split"] == "validation"]
        test = frame[frame["split"] == "test"]
        score_columns = sorted(name for name in frame if name.startswith("score_"))
        report = {}
        predictions = test[["record_id", args.group_column, args.target]].copy()
        for score in score_columns:
            fit = validation[[score, args.target]].dropna()
            calibrator = LinearRegression().fit(fit[[score]], fit[args.target])
            evaluation = test[[args.group_column, args.target, score]].dropna().copy()
            evaluation["y_pred"] = calibrator.predict(evaluation[[score]])
            evaluation = evaluation.rename(columns={args.target: "y_true"})
            metrics, per_group = evaluate_predictions(evaluation, group_column=args.group_column)
            for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy"):
                low, high = group_bootstrap_ci(per_group, metric)
                metrics[f"macro_{metric}_ci95"] = [low, high]
            metrics["calibration_slope"] = float(calibrator.coef_[0])
            metrics["calibration_intercept"] = float(calibrator.intercept_)
            report[score.removeprefix("score_")] = metrics
            predictions[score] = calibrator.predict(test[[score]])
        _write_json(args.output, report)
        predictions.to_parquet(Path(args.output).with_suffix(".predictions.parquet"), index=False)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "crossval-baseline":
        frame = _read_table(args.input).reset_index(drop=True)
        splitter = GroupKFold(n_splits=args.folds)
        prediction = pd.Series(index=frame.index, dtype=float)
        fold_id = pd.Series(index=frame.index, dtype="Int64")
        groups = frame[args.group_column].astype(str)
        for fold, (train_index, test_index) in enumerate(splitter.split(frame, groups=groups)):
            model = KmerContextRidge(k_min=args.k_min, k_max=args.k_max, alpha=args.alpha)
            model.fit(frame.iloc[train_index], target=args.target)
            prediction.iloc[test_index] = model.predict(frame.iloc[test_index])
            fold_id.iloc[test_index] = fold
            print(f"completed fold {fold + 1}/{args.folds}", flush=True)
        evaluation = frame[["record_id", args.group_column, "context_id", args.target]].copy()
        evaluation["y_true"] = evaluation[args.target]
        evaluation["y_pred"] = prediction
        evaluation["fold"] = fold_id
        metrics, per_group = evaluate_predictions(evaluation, group_column=args.group_column)
        for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy", "ndcg"):
            low, high = group_bootstrap_ci(per_group, metric)
            metrics[f"macro_{metric}_ci95"] = [low, high]
        report = {
            "design": {
                "input": args.input,
                "group_column": args.group_column,
                "folds": args.folds,
                "target": args.target,
                "model": "k-mer context ridge",
                "k_min": args.k_min,
                "k_max": args.k_max,
                "ridge_alpha": args.alpha,
            },
            **metrics,
        }
        _write_json(args.output, report)
        evaluation.to_parquet(Path(args.output).with_suffix(".predictions.parquet"), index=False)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "assay-ceiling":
        frame = _read_table(args.input)
        if "split" in frame and args.split != "all":
            frame = frame[frame["split"] == args.split]
        summary, per_group = estimate_replicate_ceiling(
            frame, args.replicates, group_column=args.group_column
        )
        _write_json(args.output, summary)
        per_group.to_csv(Path(args.output).with_suffix(".per_group.csv"), index=False)
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "crossval-embeddings":
        frame = _read_table(args.input).reset_index(drop=True)
        sequence_index, embeddings = load_embedding_archive(args.embeddings)
        splitter = GroupKFold(n_splits=args.folds)
        prediction = pd.Series(index=frame.index, dtype=float)
        fold_id = pd.Series(index=frame.index, dtype="Int64")
        groups = frame[args.group_column].astype(str)
        for fold, (train_index, test_index) in enumerate(splitter.split(frame, groups=groups)):
            model = EmbeddingContextRidge(sequence_index, embeddings, alpha=args.alpha)
            model.fit(frame.iloc[train_index], target=args.target)
            prediction.iloc[test_index] = model.predict(frame.iloc[test_index])
            fold_id.iloc[test_index] = fold
            print(f"completed fold {fold + 1}/{args.folds}", flush=True)
        evaluation = frame[["record_id", args.group_column, "context_id", args.target]].copy()
        evaluation["y_true"] = evaluation[args.target]
        evaluation["y_pred"] = prediction
        evaluation["fold"] = fold_id
        metrics, per_group = evaluate_predictions(evaluation, group_column=args.group_column)
        for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy", "ndcg"):
            low, high = group_bootstrap_ci(per_group, metric)
            metrics[f"macro_{metric}_ci95"] = [low, high]
        _write_json(args.output, metrics)
        evaluation.to_parquet(Path(args.output).with_suffix(".predictions.parquet"), index=False)
        print(json.dumps(metrics, indent=2, sort_keys=True))
    elif args.command == "crossval-intervention-embeddings":
        frame = _read_table(args.input).reset_index(drop=True)
        sequence_index, embeddings = load_embedding_archive(args.embeddings)
        splitter = GroupKFold(n_splits=args.folds)
        prediction = pd.Series(index=frame.index, dtype=float)
        fold_id = pd.Series(index=frame.index, dtype="Int64")
        groups = frame[args.group_column].astype(str)
        for fold, (train_index, test_index) in enumerate(splitter.split(frame, groups=groups)):
            model = InterventionEmbeddingRidge(sequence_index, embeddings, alpha=args.alpha)
            model.fit(frame.iloc[train_index], target=args.target)
            prediction.iloc[test_index] = model.predict(frame.iloc[test_index])
            fold_id.iloc[test_index] = fold
            print(f"completed fold {fold + 1}/{args.folds}", flush=True)
        evaluation_columns = list(
            dict.fromkeys(["record_id", args.group_column, "unit_id", args.target])
        )
        evaluation = frame[evaluation_columns].copy()
        evaluation["y_true"] = evaluation[args.target]
        evaluation["y_pred"] = prediction
        evaluation["fold"] = fold_id
        metrics, per_group = evaluate_predictions(evaluation, group_column=args.group_column)
        for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy", "ndcg"):
            low, high = group_bootstrap_ci(per_group, metric)
            metrics[f"macro_{metric}_ci95"] = [low, high]
        metrics["design"] = {
            "embedding_path": args.embeddings,
            "embedding_metadata": _embedding_metadata(args.embeddings),
            "folds": args.folds,
            "group_column": args.group_column,
            "ridge_alpha": args.alpha,
            "target": args.target,
        }
        _write_json(args.output, metrics)
        evaluation.to_parquet(Path(args.output).with_suffix(".predictions.parquet"), index=False)
        print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

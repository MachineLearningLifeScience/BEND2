#!/usr/bin/env python3
"""Build leaderboard data from paper results and reviewed submissions."""

import argparse
from pathlib import Path

from bend2.submissions import build_leaderboard


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference", type=Path, default=root / "website/data/benchmark.paper.json"
    )
    parser.add_argument("--submissions", type=Path, default=root / "submissions")
    parser.add_argument("--reviews", type=Path, default=root / "reviews")
    parser.add_argument("--preview", action="store_true", help="Include unreviewed PR candidates")
    parser.add_argument("--output", type=Path, default=root / "website/data/benchmark.json")
    args = parser.parse_args()
    data = build_leaderboard(
        args.reference, args.submissions, args.output, reviews=args.reviews, preview=args.preview
    )
    count = sum(row.get("origin") == "community" for row in data["models"])
    print(f"Built {args.output}: {count} community models")


if __name__ == "__main__":
    main()

"""Command line entry point for source acquisition through fitted models."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from possession_lab.io import collect_manifest, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["run", "analyze", "manifest", "status", "score", "train-ensemble", "efficacy"]
    )
    parser.add_argument("--sport", choices=["nfl", "nba", "nhl", "epl", "all"])
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2021, 2026)))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--height-cm", type=float)
    parser.add_argument("--weight-kg", type=float)
    parser.add_argument("--age", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--profile", type=Path, help="JSON athlete profile with explicitly named measurement units"
    )
    parser.add_argument(
        "--fast-development-fit",
        action="store_true",
        help="Small expert fit for development, not final evidence",
    )
    parser.add_argument(
        "--accept-source-updates",
        action="store_true",
        help="Accept changed upstream hashes as a new dataset version",
    )
    args = parser.parse_args()
    if args.sport is None:
        args.sport = "all" if args.command in {"efficacy", "train-ensemble"} else "nfl"
    root = args.root.resolve()
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".matplotlib"))
    if args.accept_source_updates:
        os.environ["POSSESSION_LAB_ACCEPT_SOURCE_UPDATES"] = "1"
    if args.command == "train-ensemble":
        from possession_lab.ensemble import train_ensemble

        if args.sport != "all":
            parser.error("train-ensemble trains the four-sport common contract; omit --sport")
        train_ensemble(root, fast=args.fast_development_fit)
        return
    if args.command == "efficacy":
        import json

        from possession_lab.ensemble import load_ensemble
        from possession_lab.ensemble_score import score_ensemble

        if args.profile and any(v is not None for v in [args.height_cm, args.weight_kg, args.age]):
            parser.error("Use either --profile or measurement flags, not both")
        try:
            profile = (
                json.loads(args.profile.read_text())
                if args.profile
                else {"height_cm": args.height_cm, "weight_kg": args.weight_kg, "age": args.age}
            )
            result = score_ensemble(load_ensemble(root), profile, sport=args.sport)
        except (ValueError, TypeError, OSError) as error:
            parser.error(str(error))
        if args.output:
            write_json(args.output, result)
        else:
            print(json.dumps(result, indent=2))
        return
    if args.command == "score":
        from possession_lab.predict import score_physical_profile

        if args.height_cm is None or args.weight_kg is None:
            parser.error("score requires --height-cm and --weight-kg")
        scores = {
            sport: score_physical_profile(
                root, sport, height_cm=args.height_cm, weight_kg=args.weight_kg, age=args.age
            )
            for sport in (["nfl", "nba", "nhl", "epl"] if args.sport == "all" else [args.sport])
        }
        if args.output:
            write_json(args.output, scores)
        else:
            import json

            print(json.dumps(scores, indent=2))
        return
    if args.command == "manifest":
        from possession_lab.catalog import build_catalog

        catalog = build_catalog(root)
        print(
            f"{catalog['raw_file_count']} source files; {len(catalog['processed_tables'])} processed tables"
        )
        return
    if args.command == "status":
        for sport in ["nfl", "nba", "nhl", "epl"]:
            path = root / "reports" / sport / "summary.json"
            print(f"{sport}: {path.read_text() if path.exists() else 'not run'}")
        return
    results = {}
    for sport in ["nfl", "nba", "nhl", "epl"] if args.sport == "all" else [args.sport]:
        module = importlib.import_module(f"possession_lab.sports.{sport}")
        if args.command == "analyze":
            results[sport] = module.analyze(root)
        else:
            results[sport] = module.run(root, sorted(set(args.seasons)))
        collect_manifest(root)
    latest_path = root / "reports" / "latest_run.json"
    if latest_path.exists():
        import json

        previous = json.loads(latest_path.read_text())
        previous.update(results)
        results = previous
    write_json(latest_path, results)


if __name__ == "__main__":
    main()

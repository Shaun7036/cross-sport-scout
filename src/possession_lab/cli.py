"""Command line entry point for source acquisition through fitted models."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from possession_lab.io import collect_manifest, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "analyze", "manifest", "status", "score"])
    parser.add_argument("--sport", choices=["nfl", "nba", "nhl", "epl", "all"], default="nfl")
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2021, 2026)))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--height-cm", type=float)
    parser.add_argument("--weight-kg", type=float)
    parser.add_argument("--age", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--accept-source-updates",
        action="store_true",
        help="Accept changed upstream hashes as a new dataset version",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".matplotlib"))
    if args.accept_source_updates:
        os.environ["POSSESSION_LAB_ACCEPT_SOURCE_UPDATES"] = "1"
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

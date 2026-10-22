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
        "command",
        choices=[
            "run",
            "analyze",
            "manifest",
            "status",
            "score",
            "train-ensemble",
            "efficacy",
            "build-portal",
            "portal",
            "run-all-roles",
            "analyze-all-roles",
            "train-all-roles",
            "all-roles-score",
            "build-all-roles-portal",
            "all-roles-portal",
            "build-all-roles-compact-portal",
            "all-roles-compact-portal",
            "all-roles-friendly-portal",
            "all-roles-stories-portal",
            "all-roles-report-portal",
        ],
    )
    parser.add_argument("--sport", choices=["nfl", "nba", "nhl", "epl", "all"])
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2021, 2026)))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--height-cm", type=float)
    parser.add_argument("--weight-kg", type=float)
    parser.add_argument("--age", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--port",
        type=int,
        help=(
            "Local portal port (default: 8765 legacy, 8766 detailed, 8767 compact, "
            "8768 friendly, 8769 stories, 8770 report)"
        ),
    )
    parser.add_argument("--player-id", help="Stable source-sport player identifier")
    parser.add_argument("--season", type=int, help="Player season; defaults to their latest season")
    parser.add_argument(
        "--target-sport",
        choices=["nfl", "nba", "nhl", "epl"],
        help="Limit an all-roles score to one destination sport",
    )
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
        args.sport = (
            "all"
            if args.command
            in {
                "efficacy",
                "train-ensemble",
                "build-portal",
                "portal",
                "run-all-roles",
                "analyze-all-roles",
                "train-all-roles",
                "all-roles-score",
                "build-all-roles-portal",
                "all-roles-portal",
                "build-all-roles-compact-portal",
                "all-roles-compact-portal",
                "all-roles-friendly-portal",
                "all-roles-stories-portal",
                "all-roles-report-portal",
            }
            else "nfl"
        )
    root = args.root.resolve()
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".matplotlib"))
    if args.accept_source_updates:
        os.environ["POSSESSION_LAB_ACCEPT_SOURCE_UPDATES"] = "1"
    if args.command in {
        "run-all-roles",
        "analyze-all-roles",
        "train-all-roles",
        "all-roles-score",
        "build-all-roles-portal",
        "all-roles-portal",
        "build-all-roles-compact-portal",
        "all-roles-compact-portal",
        "all-roles-friendly-portal",
        "all-roles-stories-portal",
        "all-roles-report-portal",
    }:
        import json

        from possession_lab.all_roles_eda import build_all_roles_eda
        from possession_lab.all_roles_pipeline import (
            load_all_role_models,
            run_all_roles,
            train_all_roles,
        )
        from possession_lab.all_roles_portal import build_all_roles_portal
        from possession_lab.all_roles_score import score_all_roles_profile, score_known_player

        if args.command in {"run-all-roles", "analyze-all-roles", "train-all-roles"}:
            if args.sport != "all":
                parser.error(f"{args.command} uses the common four-sport contract; omit --sport")
            if args.command == "run-all-roles":
                result = run_all_roles(root, sorted(set(args.seasons)))
                result["eda"] = build_all_roles_eda(root)
            elif args.command == "train-all-roles":
                _, report = train_all_roles(root)
                result = {"models": report["counts"], "eda": build_all_roles_eda(root)}
            else:
                result = build_all_roles_eda(root)
            print(json.dumps(result, indent=2))
            return

        if args.command == "all-roles-score":
            if args.profile and any(
                value is not None for value in [args.player_id, args.height_cm, args.weight_kg, args.age]
            ):
                parser.error("Use --profile, --player-id, or measurement flags—not a mixture")
            try:
                if args.player_id:
                    if args.sport == "all":
                        parser.error("--player-id also requires its source --sport")
                    result = score_known_player(
                        root,
                        args.sport,
                        args.player_id,
                        season=args.season,
                        target_sport=args.target_sport,
                    )
                else:
                    profile = (
                        json.loads(args.profile.read_text())
                        if args.profile
                        else {
                            "height_cm": args.height_cm,
                            "weight_kg": args.weight_kg,
                            "age": args.age,
                        }
                    )
                    result = score_all_roles_profile(
                        load_all_role_models(root), profile, target_sport=args.target_sport
                    )
            except (ValueError, TypeError, OSError) as error:
                parser.error(str(error))
            if args.output:
                write_json(args.output, result)
            else:
                print(json.dumps(result, indent=2))
            return

        if args.sport != "all":
            parser.error(f"{args.command} includes all four sports; omit --sport")
        portal_views = {
            "all-roles-portal": (8766, None, None),
            "all-roles-compact-portal": (
                8767,
                "/compact/",
                "Athlete Translation Lab Compact",
            ),
            "all-roles-friendly-portal": (
                8768,
                "/friendly/",
                "Athlete Translation Lab Friendly",
            ),
            "all-roles-stories-portal": (
                8769,
                "/stories/",
                "Athlete Translation Lab Stories",
            ),
            "all-roles-report-portal": (
                8770,
                "/report/",
                "Athlete Translation Lab Report",
            ),
        }
        default_port = portal_views.get(args.command, (8766, None, None))[0]
        port = args.port or default_port
        if not 1 <= port <= 65535:
            parser.error("--port must be between 1 and 65535")
        directory = (args.output or root / "portal-all-roles").resolve()
        try:
            if (
                args.command
                in {
                    "build-all-roles-portal",
                    "build-all-roles-compact-portal",
                }
                or not (directory / "data" / "manifest.json").exists()
            ):
                manifest = build_all_roles_portal(root, output_dir=directory)
                print(f"Exported {manifest['counts']['players']:,} players to {directory / 'data'}")
            if args.command in portal_views:
                from possession_lab.portal_server import serve_portal

                _, entry_path, label = portal_views[args.command]
                if entry_path is None:
                    serve_portal(directory, port=port)
                else:
                    serve_portal(directory, port=port, entry_path=entry_path, label=label)
        except (ValueError, TypeError, OSError) as error:
            parser.error(str(error))
        return

    if args.command in {"build-portal", "portal"}:
        from possession_lab.portal import build_portal
        from possession_lab.portal_server import serve_portal

        if args.sport != "all":
            parser.error("The portal includes all four sports; omit --sport")
        port = args.port or 8765
        if not 1 <= port <= 65535:
            parser.error("--port must be between 1 and 65535")
        directory = (args.output or root / "portal").resolve()
        try:
            if args.command == "build-portal" or not (directory / "data" / "manifest.json").exists():
                manifest = build_portal(root, output_dir=directory)
                print(f"Exported {len(manifest['players']):,} players to {directory / 'data'}")
            if args.command == "portal":
                serve_portal(directory, port=port)
        except (ValueError, TypeError, OSError) as error:
            parser.error(str(error))
        return
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

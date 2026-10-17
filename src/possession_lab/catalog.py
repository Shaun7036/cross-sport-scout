"""Generate a small tracked inventory without committing underlying source data."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from possession_lab.io import collect_manifest, write_json


def build_catalog(root: Path) -> dict:
    tables = []
    for path in sorted((root / "data" / "processed").rglob("*.parquet")):
        parquet = pq.ParquetFile(path)
        tables.append(
            {
                "path": str(path.relative_to(root)),
                "rows": parquet.metadata.num_rows,
                "row_groups": parquet.metadata.num_row_groups,
                "columns": [{"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow],
            }
        )
    manifest = collect_manifest(root)
    summaries = {}
    for sport in ["nfl", "nba", "nhl", "epl"]:
        path = root / "reports" / sport / "summary.json"
        if path.exists():
            summary = json.loads(path.read_text())
            summaries[sport] = {
                "eda": summary.get("eda"),
                "forecast_status": summary.get("forecast", {}).get("status"),
                "physical_role_status": summary.get("physical_role_model", {}).get("status"),
                "limitations": summary.get("limitations"),
            }
    result = {
        "raw_file_count": manifest["file_count"],
        "raw_bytes": manifest["bytes"],
        "processed_tables": tables,
        "sports": summaries,
    }
    write_json(root / "metadata" / "dataset_catalog.json", result)
    lines = [
        "# Data inventory",
        "",
        f"{manifest['file_count']} cached source files; {manifest['bytes'] / 1024**2:.1f} MiB before derived tables.",
        "",
        "The raw files, processed player tables and fitted binary models are local artifacts.",
        "Re-run the command line pipeline to recreate them from the tracked source manifest.",
        "",
        "| Sport | Seasons | Player-seasons | Distinct athletes | Forecast |",
        "|---|---|---:|---:|---|",
    ]
    for sport, summary in summaries.items():
        eda = summary["eda"]
        lines.append(
            f"| {sport.upper()} | {', '.join(map(str, eda['seasons']))} | {eda['rows']:,} | "
            f"{eda['unique_players']:,} | {summary['forecast_status']} |"
        )
    lines.extend(["", "## Processed tables", "", "| Table | Rows | Columns |", "|---|---:|---:|"])
    for table in tables:
        lines.append(f"| {table['path']} | {table['rows']:,} | {len(table['columns'])} |")
    lines.extend(
        [
            "",
            "Field names and types are in dataset_catalog.json; download URLs, SHA-256 hashes, "
            "access timestamps and source terms are in download_manifest.json.",
            "",
        ]
    )
    (root / "metadata" / "data_inventory.md").write_text("\n".join(lines))
    return result

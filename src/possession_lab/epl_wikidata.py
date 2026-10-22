"""Rights-cleared EPL physical-profile enrichment from Wikidata.

FBref cannot be used as a model-training source under the current Sports
Reference terms and no longer exposes its former advanced soccer feed.  This
module therefore implements the deliberately narrow fallback requested for
physical coverage: exact English label (or alias) plus exact date-of-birth
matches against Wikidata's CC0 structured data.

The resulting height and mass values are profile facts, not season-specific
measurements.  Ambiguous identities and conflicting quantities are quarantined
rather than guessed.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests

from possession_lab.io import sha256, write_json

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "AthleteTranslationLab/0.1 "
    "(academic sports analytics; https://github.com/Shaun7036/cross-sport-scout)"
)
WIKIDATA_LICENSE_NOTE = (
    "Wikidata structured data are CC0. Exact English label/alias plus exact date of birth "
    "is required; community-maintained height and mass are undated profile facts."
)


def _escape_sparql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _latest_identity_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one queryable row per athlete with a known exact birth date."""
    source = frame.copy()
    source = source.loc[source["role"].isin(["GK", "DEF", "MID", "FWD"])].copy()
    dob_columns = [column for column in ["date_of_birth_fpl", "date_of_birth"] if column in source]
    if not dob_columns:
        return pd.DataFrame(columns=["player_id", "name", "date_of_birth"])
    dob = pd.Series(pd.NaT, index=source.index, dtype="datetime64[ns, UTC]")
    for column in dob_columns:
        candidate = pd.to_datetime(source[column], errors="coerce", utc=True)
        dob = dob.combine_first(candidate)
    source["date_of_birth"] = dob
    source = source.loc[source["date_of_birth"].notna() & source["name"].notna()].copy()
    source["name"] = source["name"].astype(str).str.strip()
    source = source.loc[source["name"].ne("")].copy()
    return (
        source.sort_values(["player_id", "season"])
        .drop_duplicates("player_id", keep="last")
        [["player_id", "name", "date_of_birth"]]
        .reset_index(drop=True)
    )


def _query_for_names(names: Iterable[str]) -> str:
    values = " ".join(f'"{_escape_sparql_literal(name)}"@en' for name in names)
    return f"""
SELECT ?item ?matchedLabel ?dob
       ?height ?heightUnit ?mass ?massUnit
WHERE {{
  VALUES ?matchedLabel {{ {values} }}
  {{ ?item rdfs:label ?matchedLabel. }}
  UNION
  {{ ?item skos:altLabel ?matchedLabel. }}
  ?item wdt:P31 wd:Q5;
        wdt:P569 ?dob.
  OPTIONAL {{
    ?item p:P2048/psv:P2048 ?heightNode.
    ?heightNode wikibase:quantityAmount ?height;
                wikibase:quantityUnit ?heightUnit.
  }}
  OPTIONAL {{
    ?item p:P2067/psv:P2067 ?massNode.
    ?massNode wikibase:quantityAmount ?mass;
              wikibase:quantityUnit ?massUnit.
  }}
}}
""".strip()


def _request_sparql(
    query: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 60,
    attempts: int = 4,
) -> dict[str, Any]:
    client = session or requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
        "Accept-Encoding": "gzip",
    }
    for attempt in range(attempts):
        response = client.post(
            SPARQL_ENDPOINT,
            data={"query": query, "format": "json"},
            headers=headers,
            timeout=timeout,
        )
        if response.status_code == 429:
            delay = float(response.headers.get("Retry-After", 2 ** (attempt + 1)))
            time.sleep(min(max(delay, 1.0), 60.0))
            continue
        if response.status_code >= 500 and attempt + 1 < attempts:
            time.sleep(float(2 ** attempt))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Wikidata query was rate-limited after all retry attempts")


def _unit_id(binding: dict[str, Any], key: str) -> str | None:
    value = binding.get(key, {}).get("value")
    return str(value).rsplit("/", 1)[-1] if value else None


def _quantity(binding: dict[str, Any], value_key: str, unit_key: str, *, kind: str) -> float:
    raw = binding.get(value_key, {}).get("value")
    unit = _unit_id(binding, unit_key)
    if raw is None or unit is None:
        return np.nan
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return np.nan
    if kind == "height":
        factors = {
            "Q11573": 100.0,
            "Q174728": 1.0,
            "Q218593": 0.1,
            "Q3710": 30.48,
            "Q253276": 2.54,
        }
        converted = value * factors.get(unit, np.nan)
        return converted if np.isfinite(converted) and 140 <= converted <= 230 else np.nan
    factors = {"Q11570": 1.0, "Q100995": 0.001, "Q453185": 0.45359237}
    converted = value * factors.get(unit, np.nan)
    return converted if np.isfinite(converted) and 35 <= converted <= 230 else np.nan


def _collapsed_quantity(values: pd.Series, *, tolerance: float) -> tuple[float, str]:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    if not len(clean):
        return np.nan, "missing"
    if float(np.ptp(clean)) > tolerance:
        return np.nan, "quarantined_conflicting_values"
    return float(np.median(clean)), "accepted"


def parse_wikidata_results(payloads: Iterable[dict[str, Any]], identities: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Parse raw SPARQL responses and enforce strict identity/value gates."""
    bindings: list[dict[str, Any]] = []
    for payload in payloads:
        bindings.extend(payload.get("results", {}).get("bindings", []))
    rows = []
    for binding in bindings:
        qid = str(binding.get("item", {}).get("value", "")).rsplit("/", 1)[-1]
        label = binding.get("matchedLabel", {}).get("value")
        dob = pd.to_datetime(binding.get("dob", {}).get("value"), errors="coerce", utc=True)
        if not qid or not label or pd.isna(dob):
            continue
        rows.append(
            {
                "qid": qid,
                "matched_label": str(label),
                "date_of_birth": dob.normalize(),
                "height_cm_candidate": _quantity(binding, "height", "heightUnit", kind="height"),
                "weight_kg_candidate": _quantity(binding, "mass", "massUnit", kind="mass"),
            }
        )
    raw = pd.DataFrame(rows)
    output_rows: list[dict[str, Any]] = []
    ambiguous_players = 0
    for identity in identities.itertuples(index=False):
        expected_dob = pd.Timestamp(identity.date_of_birth).tz_convert("UTC").normalize()
        if raw.empty:
            candidates = raw
        else:
            candidates = raw.loc[
                raw["matched_label"].eq(str(identity.name))
                & raw["date_of_birth"].eq(expected_dob)
            ]
        qids = sorted(candidates["qid"].dropna().unique()) if not candidates.empty else []
        if len(qids) != 1:
            ambiguous_players += int(len(qids) > 1)
            continue
        qid = qids[0]
        entity = candidates.loc[candidates["qid"].eq(qid)]
        height, height_status = _collapsed_quantity(
            entity["height_cm_candidate"], tolerance=5.0
        )
        weight, weight_status = _collapsed_quantity(
            entity["weight_kg_candidate"], tolerance=5.0
        )
        if not np.isfinite(height) and not np.isfinite(weight):
            continue
        output_rows.append(
            {
                "player_id": str(identity.player_id),
                "wikidata_qid": qid,
                "wikidata_matched_label": str(identity.name),
                "wikidata_date_of_birth": expected_dob,
                "wikidata_height_cm": height,
                "wikidata_weight_kg": weight,
                "wikidata_height_status": height_status,
                "wikidata_weight_status": weight_status,
                "wikidata_match_method": "exact_english_label_or_alias_and_exact_birth_date",
                "wikidata_source": "Wikidata structured data (CC0)",
                "wikidata_temporality": (
                    "community-maintained undated profile; not a season measurement"
                ),
            }
        )
    profiles = pd.DataFrame(output_rows)
    if profiles.empty:
        profiles = pd.DataFrame(
            columns=[
                "player_id",
                "wikidata_qid",
                "wikidata_matched_label",
                "wikidata_date_of_birth",
                "wikidata_height_cm",
                "wikidata_weight_kg",
                "wikidata_height_status",
                "wikidata_weight_status",
                "wikidata_match_method",
                "wikidata_source",
                "wikidata_temporality",
            ]
        )
    audit = {
        "queryable_identities": int(len(identities)),
        "raw_bindings": int(len(raw)),
        "accepted_identities": int(len(profiles)),
        "accepted_height_identities": int(profiles["wikidata_height_cm"].notna().sum()),
        "accepted_weight_identities": int(profiles["wikidata_weight_kg"].notna().sum()),
        "ambiguous_identity_matches_quarantined": int(ambiguous_players),
        "identity_rule": "exact English label or alias plus exact date of birth",
        "quantity_rule": (
            "recognized metric/imperial unit, plausible range, and no >5-unit conflict per entity"
        ),
    }
    return profiles, audit


def fetch_epl_wikidata_profiles(
    root: Path | str,
    *,
    batch_size: int = 35,
    delay_seconds: float = 1.0,
    force: bool = False,
) -> dict:
    """Fetch and cache strict Wikidata matches for the canonical EPL identities."""
    root = Path(root)
    canonical_path = root / "data" / "processed" / "epl" / "player_seasons.parquet"
    if not canonical_path.exists():
        raise FileNotFoundError(f"Build the EPL base panel first: {canonical_path}")
    identities = _latest_identity_rows(pd.read_parquet(canonical_path))
    raw_dir = root / "data" / "raw" / "epl" / "wikidata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    identity_payload = [
        {
            "player_id": str(row.player_id),
            "name": str(row.name),
            "date_of_birth": pd.Timestamp(row.date_of_birth).date().isoformat(),
        }
        for row in identities.itertuples(index=False)
    ]
    identity_hash = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payloads = []
    session = requests.Session()
    batches = [
        identities.iloc[index : index + batch_size]
        for index in range(0, len(identities), batch_size)
    ]
    for index, batch in enumerate(batches, start=1):
        query = _query_for_names(batch["name"].drop_duplicates().tolist())
        path = raw_dir / f"query_{index:03d}.json"
        sidecar = path.with_name(path.name + ".source.json")
        reusable = False
        if path.exists() and sidecar.exists() and not force:
            metadata = json.loads(sidecar.read_text())
            reusable = (
                metadata.get("identity_hash") == identity_hash
                and metadata.get("query_sha256")
                == hashlib.sha256(query.encode("utf-8")).hexdigest()
                and metadata.get("sha256") == sha256(path)
            )
        if reusable:
            payload = json.loads(path.read_text())
        else:
            payload = _request_sparql(query, session=session)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            write_json(
                sidecar,
                {
                    "url": SPARQL_ENDPOINT,
                    "method": "POST",
                    "source": "Wikidata Query Service",
                    "license_note": WIKIDATA_LICENSE_NOTE,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "identity_hash": identity_hash,
                    "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                    "batch": index,
                    "batch_count": len(batches),
                },
            )
            if index < len(batches):
                time.sleep(max(0.0, float(delay_seconds)))
        payloads.append(payload)
    profiles, audit = parse_wikidata_results(payloads, identities)
    profiles_path = raw_dir / "profiles.parquet"
    profiles.to_parquet(profiles_path, index=False)
    audit.update(
        {
            "status": "complete",
            "source": "Wikidata Query Service",
            "source_url": SPARQL_ENDPOINT,
            "license": "CC0",
            "identity_hash": identity_hash,
            "batches": len(batches),
            "profiles_path": str(profiles_path.relative_to(root)),
            "temporality": "undated profile facts; never annual measurements",
        }
    )
    write_json(root / "reports" / "epl" / "wikidata_physical_enrichment.json", audit)
    return audit


def attach_wikidata_physical(frame: pd.DataFrame, profiles: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fill only missing profile facts while retaining source and timing labels."""
    source = frame.copy()
    before_height = int(source["height_cm"].notna().sum())
    before_weight = int(source["weight_kg"].notna().sum())
    merged = source.merge(profiles, on="player_id", how="left", validate="many_to_one")
    height_missing = pd.to_numeric(merged["height_cm"], errors="coerce").isna()
    weight_missing = pd.to_numeric(merged["weight_kg"], errors="coerce").isna()
    height_fill = height_missing & pd.to_numeric(
        merged["wikidata_height_cm"], errors="coerce"
    ).notna()
    weight_fill = weight_missing & pd.to_numeric(
        merged["wikidata_weight_kg"], errors="coerce"
    ).notna()
    merged.loc[height_fill, "height_cm"] = merged.loc[height_fill, "wikidata_height_cm"]
    merged.loc[weight_fill, "weight_kg"] = merged.loc[weight_fill, "wikidata_weight_kg"]
    used = height_fill | weight_fill
    existing_source = merged.get("physical_source", pd.Series(pd.NA, index=merged.index)).astype("string")
    merged.loc[used & existing_source.isna(), "physical_source"] = "Wikidata structured data (CC0)"
    merged.loc[used & existing_source.notna(), "physical_source"] = (
        existing_source.loc[used & existing_source.notna()] + "; Wikidata CC0 missing-field fill"
    )
    merged.loc[used, "physical_temporality"] = (
        "undated community profile; propagated across seasons and not an annual measurement"
    )
    merged["wikidata_physical_used"] = used
    audit = {
        "rows": int(len(merged)),
        "profile_identities_available": int(profiles["player_id"].nunique()),
        "rows_filled_height": int(height_fill.sum()),
        "rows_filled_weight": int(weight_fill.sum()),
        "height_rows_before": before_height,
        "height_rows_after": int(merged["height_cm"].notna().sum()),
        "weight_rows_before": before_weight,
        "weight_rows_after": int(merged["weight_kg"].notna().sum()),
        "overwrites_existing_values": 0,
    }
    return merged, audit


def load_and_attach_wikidata(root: Path | str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    path = Path(root) / "data" / "raw" / "epl" / "wikidata" / "profiles.parquet"
    if not path.exists():
        return frame.copy(), {
            "status": "not_cached",
            "instruction": "Run `possession-lab enrich-epl-wikidata --root .`.",
        }
    profiles = pd.read_parquet(path)
    enriched, audit = attach_wikidata_physical(frame, profiles)
    return enriched, {"status": "applied", **audit}

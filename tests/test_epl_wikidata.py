import numpy as np
import pandas as pd
import pytest

from possession_lab.epl_wikidata import (
    _latest_identity_rows,
    attach_wikidata_physical,
    parse_wikidata_results,
)


def _binding(
    *,
    qid="Q1",
    label="Example Player",
    dob="2000-01-02T00:00:00Z",
    height="1.80",
    height_unit="Q11573",
    mass="80",
    mass_unit="Q11570",
):
    row = {
        "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "matchedLabel": {"value": label},
        "dob": {"value": dob},
    }
    if height is not None:
        row["height"] = {"value": height}
        row["heightUnit"] = {
            "value": f"http://www.wikidata.org/entity/{height_unit}"
        }
    if mass is not None:
        row["mass"] = {"value": mass}
        row["massUnit"] = {"value": f"http://www.wikidata.org/entity/{mass_unit}"}
    return row


def test_latest_identity_rows_requires_dob_and_keeps_latest_name():
    frame = pd.DataFrame(
        {
            "player_id": ["fpl:1", "fpl:1", "fpl:2"],
            "name": ["Old Name", "Example Player", "Unknown"],
            "season": [2021, 2025, 2025],
            "role": ["MID", "MID", "FWD"],
            "date_of_birth_fpl": ["2000-01-02", "2000-01-02", None],
        }
    )

    result = _latest_identity_rows(frame)

    assert result["player_id"].tolist() == ["fpl:1"]
    assert result.loc[0, "name"] == "Example Player"


def test_wikidata_parser_converts_units_and_requires_exact_dob():
    identities = pd.DataFrame(
        {
            "player_id": ["fpl:1", "fpl:2"],
            "name": ["Example Player", "Wrong Birthday"],
            "date_of_birth": pd.to_datetime(
                ["2000-01-02", "2001-02-03"], utc=True
            ),
        }
    )
    payload = {
        "results": {
            "bindings": [
                _binding(),
                _binding(
                    qid="Q2",
                    label="Wrong Birthday",
                    dob="2001-02-04T00:00:00Z",
                    height="72",
                    height_unit="Q253276",
                    mass="180",
                    mass_unit="Q453185",
                ),
            ]
        }
    }

    profiles, audit = parse_wikidata_results([payload], identities)

    assert profiles["player_id"].tolist() == ["fpl:1"]
    assert profiles.loc[0, "wikidata_height_cm"] == pytest.approx(180.0)
    assert profiles.loc[0, "wikidata_weight_kg"] == pytest.approx(80.0)
    assert audit["accepted_identities"] == 1


def test_wikidata_parser_quarantines_ambiguous_entity_and_conflicting_quantity():
    identities = pd.DataFrame(
        {
            "player_id": ["fpl:1", "fpl:2"],
            "name": ["Ambiguous Player", "Conflict Player"],
            "date_of_birth": pd.to_datetime(
                ["2000-01-02", "2001-02-03"], utc=True
            ),
        }
    )
    payload = {
        "results": {
            "bindings": [
                _binding(qid="Q1", label="Ambiguous Player"),
                _binding(qid="Q9", label="Ambiguous Player"),
                _binding(
                    qid="Q2",
                    label="Conflict Player",
                    dob="2001-02-03T00:00:00Z",
                    height="170",
                    height_unit="Q174728",
                    mass=None,
                ),
                _binding(
                    qid="Q2",
                    label="Conflict Player",
                    dob="2001-02-03T00:00:00Z",
                    height="190",
                    height_unit="Q174728",
                    mass=None,
                ),
            ]
        }
    }

    profiles, audit = parse_wikidata_results([payload], identities)

    assert profiles.empty
    assert audit["ambiguous_identity_matches_quarantined"] == 1


def test_attach_wikidata_fills_missing_only_and_preserves_profile_temporality():
    frame = pd.DataFrame(
        {
            "player_id": ["fpl:1", "fpl:2"],
            "height_cm": [np.nan, 191.0],
            "weight_kg": [75.0, np.nan],
            "physical_source": [pd.NA, "ESPN"],
            "physical_temporality": [pd.NA, "undated ESPN profile"],
        }
    )
    profiles = pd.DataFrame(
        {
            "player_id": ["fpl:1", "fpl:2"],
            "wikidata_qid": ["Q1", "Q2"],
            "wikidata_height_cm": [180.0, 180.0],
            "wikidata_weight_kg": [80.0, 85.0],
            "wikidata_match_method": ["strict", "strict"],
        }
    )

    result, audit = attach_wikidata_physical(frame, profiles)

    assert result.loc[0, "height_cm"] == 180.0
    assert result.loc[0, "weight_kg"] == 75.0
    assert result.loc[1, "height_cm"] == 191.0
    assert result.loc[1, "weight_kg"] == 85.0
    assert audit["overwrites_existing_values"] == 0
    assert audit["rows_filled_height"] == 1
    assert audit["rows_filled_weight"] == 1
    assert result["wikidata_physical_used"].all()
    assert result["physical_temporality"].str.contains("not an annual measurement").all()

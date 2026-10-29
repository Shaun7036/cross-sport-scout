import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_every_featured_player_has_one_cross_sport_story() -> None:
    manifest = _read_json(SITE / "public" / "data" / "manifest.json")
    catalog = _read_json(SITE / "src" / "data" / "featured-stories.json")

    stories = catalog["stories"]
    featured_ids = [case["player_id"] for case in manifest["featured_cases"]]
    players = {player["id"]: player for player in manifest["featured_players"]}
    sports = {
        sport["id"]: {role["id"] for role in sport["roles"]}
        for sport in manifest["sports"]
    }

    assert len(stories) == 14
    assert [story["player_id"] for story in stories] == featured_ids
    assert len({story["player_id"] for story in stories}) == 14
    assert len({story["slug"] for story in stories}) == 14

    for story in stories:
        player = players[story["player_id"]]
        assert story["slug"]
        assert story["tag"]
        assert story["noticed"]
        assert story["logic"]
        assert story["caution"]
        assert story["target_sport"] != player["sport"]
        assert story["target_role"] in sports[story["target_sport"]]

        detail = _read_json(SITE / "public" / player["detail_path"])
        target = detail["targets"][story["target_sport"]]["roles"][story["target_role"]]
        native_value = detail["native"]["observed"]["value"]
        assert isinstance(native_value, (int, float))
        assert story["native_score"] == round(native_value, 1)

        transfer = target["transfer"]
        assert transfer["status"] == "available" or transfer["status"].startswith("withheld_")
        assert story["fit_status"] == transfer["status"]
        if transfer["value"] is None:
            assert transfer["status"].startswith("withheld_")
            assert story["fit_score"] is None
        else:
            assert story["fit_score"] == round(transfer["value"], 1)

        body = target["body_fit"]
        assert story["body_score"] == round(body["value"], 1)
        assert story["body_outside"] is bool(body["outside_1_99_reference"])


def test_featured_compatibility_page_points_to_combined_stories() -> None:
    featured = (SITE / "src" / "pages" / "featured" / "index.astro").read_text()
    explorer = (SITE / "src" / "pages" / "explorer" / "index.astro").read_text()

    assert 'href={`${href("stories/")}#featured-players`}' in featured
    assert 'href={`${href("stories/")}#featured-players`}' in explorer

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from possession_lab.all_roles_report import build_feature_payload, build_validation_payload

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "portal-all-roles" / "report"
PAGES = (
    "index.html",
    "findings.html",
    "features.html",
    "validation.html",
    "visuals.html",
    "guide.html",
)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self.ids = set()
        self.h1_count = 0
        self.has_description = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "h1":
            self.h1_count += 1
        if tag == "meta" and values.get("name") == "description" and values.get("content"):
            self.has_description = True


def parse_page(name):
    parser = PageParser()
    parser.feed((REPORT / name).read_text())
    return parser


def test_report_has_complete_plain_language_pages():
    for name in PAGES:
        page = REPORT / name
        assert page.exists()
        text = page.read_text()
        parser = parse_page(name)
        assert text.lower().startswith("<!doctype html>")
        assert parser.h1_count == 1
        assert parser.has_description
        assert "styles.css" in text
        assert "not a" in text.lower() or "does not" in text.lower()


def test_report_local_links_resolve():
    for name in PAGES:
        parser = parse_page(name)
        for href in parser.links:
            parsed = urlparse(href)
            assert not parsed.scheme, f"Unexpected external link in {name}: {href}"
            path = parsed.path
            if not path:
                continue
            target = (REPORT / path).resolve()
            if path.endswith("/"):
                target /= "index.html"
            assert target.is_file(), f"Broken link in {name}: {href}"
            if parsed.fragment and target.parent == REPORT:
                assert parsed.fragment in parse_page(target.name).ids


def test_report_preserves_the_main_evidence_boundaries():
    journey = (REPORT / "index.html").read_text()
    findings = (REPORT / "findings.html").read_text()
    visuals = (REPORT / "visuals.html").read_text()
    guide = (REPORT / "guide.html").read_text()

    for value in ("27,652", "10,311", "19,197"):
        assert value in journey
    for value in ("15,518", "2,866", "5,263", "4,005"):
        assert value in findings
    assert "4" in findings and "physical heads" in findings
    assert "experimental" in findings.lower()
    assert "not a transfer probability" in findings.lower()
    for value in ("15,518", "34.9%", "23", "286", "125", "10"):
        assert value in visuals
    assert "0" in visuals and "deployment-ready" in visuals
    assert "analogy, not a success forecast" in visuals.lower()
    assert "No score is not a zero" in guide
    assert "reaction speed" in guide
    assert "not included in trained models" in guide.lower()
    assert "not athlete-disjoint" in guide


def test_report_uses_only_local_static_assets():
    assets = [REPORT / "styles.css", REPORT / "features.js", REPORT / "validation.js"]
    for path in (*[REPORT / name for name in PAGES], *assets):
        text = path.read_text()
        assert "http://" not in text.lower()
        assert "https://" not in text.lower()
    for name in PAGES:
        for source in parse_page(name).scripts:
            assert not urlparse(source).scheme
            assert (REPORT / source).is_file()
    for path in (REPORT / "features.js", REPORT / "validation.js"):
        script = path.read_text()
        assert "innerHTML" not in script
        assert "textContent" in script


def test_feature_dictionary_is_generated_from_the_complete_role_registry():
    expected = build_feature_payload(ROOT)
    exported = json.loads((REPORT / "data" / "features.json").read_text())

    assert exported == expected
    assert exported["role_count"] == 26
    assert len(exported["dimensions"]) == 7
    assert sum(len(sport["roles"]) for sport in exported["sports"]) == 26
    assert any(not role["domains"] for sport in exported["sports"] for role in sport["roles"])


def test_validation_page_uses_saved_evidence_and_separates_the_ensemble():
    expected = build_validation_payload(ROOT)
    exported = json.loads((REPORT / "data" / "validation.json").read_text())

    assert exported == expected
    assert exported["all_roles"]["frozen_test_season"] == 2025
    assert exported["all_roles"]["counts"]["physical_heads_fit"] == 23
    assert exported["all_roles"]["counts"]["native_heads_fit"] == 23
    assert exported["all_roles"]["counts"]["native_profile_heads_fit"] == 23
    assert exported["all_roles"]["counts"]["bridge_heads_fit"] == 286
    assert exported["ensemble"]["separate_study"] is True
    assert "possession" in exported["ensemble"]["title"].lower()
    assert all(
        row["training_label_policy"]
        for sport in exported["all_roles"]["sports"]
        for family in (sport["physical"], sport["native"], sport["native_profile"])
        for row in family
        if row["test_n"] is not None
    )


def test_new_report_pages_keep_the_evidence_boundaries_visible():
    features = (REPORT / "features.html").read_text().lower()
    validation = (REPORT / "validation.html").read_text().lower()
    validation_script = (REPORT / "validation.js").read_text().lower()

    assert "game iq" in features
    assert "not identical" in features
    assert "reduced weight" in features
    assert "not cross-sport validation" in validation
    assert "build + canonical playing profile" in validation
    assert "separate historical study" in validation
    assert "not deployment approval" in validation_script
    assert "not the model family" in validation_script

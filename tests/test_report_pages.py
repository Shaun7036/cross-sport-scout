from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parents[1]
REPORT = ROOT / "portal-all-roles" / "report"
PAGES = ("index.html", "findings.html", "guide.html")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.h1_count = 0
        self.has_description = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "h1":
            self.h1_count += 1
        if tag == "meta" and values.get("name") == "description" and values.get("content"):
            self.has_description = True


def parse_page(name):
    parser = PageParser()
    parser.feed((REPORT / name).read_text())
    return parser


def test_report_has_three_complete_plain_language_pages():
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
    guide = (REPORT / "guide.html").read_text()

    for value in ("27,652", "10,311", "19,197"):
        assert value in journey
    for value in ("15,518", "2,866", "5,263", "4,005"):
        assert value in findings
    assert "4" in findings and "physical heads" in findings
    assert "experimental" in findings.lower()
    assert "not a transfer probability" in findings.lower()
    assert "No score is not a zero" in guide
    assert "reaction speed" in guide
    assert "not included in trained models" in guide.lower()
    assert "not athlete-disjoint" in guide


def test_report_uses_only_local_static_assets():
    for path in (*[REPORT / name for name in PAGES], REPORT / "styles.css"):
        text = path.read_text()
        assert "<script" not in text.lower()
        assert "http://" not in text.lower()
        assert "https://" not in text.lower()

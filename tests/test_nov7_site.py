"""Nov7-only offline assertions, added beside unchanged historical regressions."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import unittest
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "tests/nov7_expected.json").read_text())
BRAND = EXPECTED["brand"]
BASE_COMMIT = "17a1d167a4105900f19c4db59d4aaddad102de1c"
DATE = "2026-11-07"
OLD = "2026-11-06"
ORIGIN = f"https://{BRAND}.com/"
FIXTURE_EDITS = {
    "factsfirstdaily": {
        "tests/interactions.test.cjs": [
            ("assert.equal(config.editions[0].date, '2026-11-06');",
             "assert.equal(config.editions[0].date, '2026-11-07');"),
            ("assert.equal(config.editions[0].url, 'https://factsfirstdaily.com/editions/2026-11-06.html');",
             "assert.equal(config.editions[0].url, 'https://factsfirstdaily.com/editions/2026-11-07.html');"),
            ("assert.equal(config.editions.length, 5);", "assert.equal(config.editions.length, 6);"),
            ("homepage configuration and all 5 edition destinations.",
             "homepage configuration and all 6 edition destinations."),
        ],
        "tests/links_test.py": [
            ("""    assert 'href="/editions/2026-11-06.html">Latest edition' in p.read_text()""",
             """    expected_latest = "2026-11-07" if p.name == "2026-11-07.html" else "2026-11-06"
    assert f'href="/editions/{expected_latest}.html">Latest edition' in p.read_text()"""),
        ],
    },
    "thedailyskim": {
        "tests/test_site.py": [
            ("'editions/2026-11-06.html','editions/2026-11-05.html','editions/2026-11-03.html',",
             "'editions/2026-11-07.html','editions/2026-11-06.html','editions/2026-11-05.html','editions/2026-11-03.html',"),
            ("""href="editions/2026-11-06.html#',home)),5)""",
             """href="editions/2026-11-07.html#',home)),5)"""),
            ("self.assertEqual(count,7)", "self.assertEqual(count,8)"),
            ("self.assertEqual(cases,35)", "self.assertEqual(cases,42)"),
        ],
    },
    "worldskim": {
        "tests/links.test.py": [
            ("== ['editions/2026-11-06.html', 'editions/2026-11-03.html',",
             "== ['editions/2026-11-07.html', 'editions/2026-11-06.html', 'editions/2026-11-03.html',"),
        ],
    },
}


def original(path):
    return subprocess.check_output(["git", "show", f"{BASE_COMMIT}:{path}"], cwd=ROOT, text=True)


def soup(path):
    return BeautifulSoup((ROOT / path).read_text(), "html.parser")


def config(path):
    text = (ROOT / path).read_text()
    match = re.search(r"(?:const|var) SITE_CONFIG\s*=\s*(\{.*?\});", text, re.S)
    assert match
    # Only the data expression is evaluated; no site/form behavior is executed.
    return json.loads(subprocess.check_output(
        ["node", "-e", "process.stdout.write(JSON.stringify((" + match[1] + ")))"], text=True))


class Nov7Site(unittest.TestCase):
    def test_current_card_and_prior_card_retained(self):
        paths = ["index.html"] + (["archive.html"] if BRAND == "worldskim" else ["editions/index.html"] if BRAND == "factsfirstdaily" else [])
        for path in paths:
            rows = config(path)["editions"]
            self.assertTrue(rows[0]["url"].endswith(f"editions/{DATE}.html"))
            self.assertEqual(rows[0]["description"], EXPECTED["description"])
            title = "\n".join(rows[0]["title"]) if isinstance(rows[0]["title"], list) else rows[0]["title"]
            self.assertEqual(title, EXPECTED["title"])
            self.assertTrue(any(r["url"].endswith(f"editions/{OLD}.html") for r in rows))

    def test_all_internal_links_assets_and_anchors(self):
        pages = {p.resolve(): BeautifulSoup(p.read_text(), "html.parser") for p in ROOT.rglob("*.html") if ".git" not in p.parts}
        for path, doc in pages.items():
            for node in doc.select("[href],[src]"):
                raw = node.get("href", node.get("src", ""))
                if path.parent.name == "email" and raw == "{!remove_web}":
                    continue  # Historical AWeber email token, not a website path.
                target = urlsplit(urljoin(ORIGIN + path.relative_to(ROOT).as_posix(), raw))
                if target.scheme != "https" or target.hostname != BRAND + ".com":
                    continue
                file = ROOT / unquote(target.path).lstrip("/")
                if file.is_dir():
                    file /= "index.html"
                self.assertTrue(file.is_file(), (str(path), raw))
                if target.fragment and file.resolve() in pages:
                    self.assertIsNotNone(pages[file.resolve()].find(id=unquote(target.fragment)), (str(path), raw))

    def test_new_and_previous_navigation(self):
        new = soup(f"editions/{DATE}.html")
        nav = new.select_one("nav.nav,nav.ednav,nav.ed-nav")
        self.assertEqual(nav.find("a")["href"], OLD + ".html")
        old = soup(f"editions/{OLD}.html")
        self.assertIsNotNone(old.find("a", href=DATE + ".html"))
        for a in new.select("footer a[href]"):
            if a.get_text(" ", strip=True) in ("Latest edition", "Today's edition", "Today's trivia", "Daily trivia"):
                self.assertIn(DATE, a["href"])

    def test_current_content_and_locked_style_scripts(self):
        new = soup(f"editions/{DATE}.html")
        base = BeautifulSoup(original(f"editions/{OLD}.html"), "html.parser")
        self.assertEqual([str(n) for n in new.select("style,script,link[rel=stylesheet]")],
                         [str(n) for n in base.select("style,script,link[rel=stylesheet]")])
        for path in [f"editions/{OLD}.html"]:
            old = soup(path)
            self.assertEqual([str(n) for n in old.select("article.story,#deep-dive,#tri,.poll,#reader-poll")],
                             [str(n) for n in base.select("article.story,#deep-dive,#tri,.poll,#reader-poll")])
        self.assertEqual([a.h3.get_text(" ", strip=True) for a in new.select("article.story")],
                         [a["title"] for a in EXPECTED["stories"]])
        self.assertEqual(new.select_one("#dd-h").get_text(" ", strip=True), EXPECTED["deep_dive"]["title"])
        # New-page historical recommendation photographs and all fixed images untouched.
        def fixed_images(doc):
            return [dict(i.attrs) for i in doc.select("img") if not i.find_parent("article", class_="story") and not i.find_parent(id="deep-dive")]
        self.assertEqual(fixed_images(new), fixed_images(base))

    def test_poll_trivia_sources_and_share_dates(self):
        new = soup(f"editions/{DATE}.html")
        poll = new.select_one(".poll,#reader-poll")
        self.assertIn(EXPECTED["poll"]["question"], poll.get_text(" ", strip=True))
        self.assertEqual(len(poll.select("a")), 2)
        self.assertEqual({parse_qs(urlsplit(a["href"]).query)["vote"][0] for a in poll.select("a")}, {"yes", "no"})
        for a in poll.select("a"):
            self.assertEqual(parse_qs(urlsplit(a["href"]).query)["poll"], [EXPECTED["poll"]["slug"]])
        self.assertIn(EXPECTED["trivia"]["question"], new.select_one("#tri").get_text(" ", strip=True))
        self.assertEqual(len(new.select("#tri .qz-opt")), 4)
        self.assertEqual(new.select_one("#tri")["data-answer"], str("ABCD".index(EXPECTED["trivia"]["correct_letter"])))
        shares = [a["href"] for a in new.select("a[href]") if any(x in a["href"] for x in
                  ("mailto:?subject=", "facebook.com/sharer/", "twitter.com/intent/", "threads.net/intent/",
                   "linkedin.com/sharing/", "reddit.com/submit", "wa.me/?"))]
        # Approved Daily Skim baseline has no share controls. Do not invent a UI.
        self.assertGreaterEqual(len(shares), 0 if BRAND == "thedailyskim" else 5)
        for href in shares:
            flat = " ".join(v for vs in parse_qs(urlsplit(href).query).values() for v in vs)
            self.assertIn(f"https://{BRAND}.com/editions/{DATE}.html", flat)
            self.assertNotIn(OLD + ".html", flat)
        # URL correctness alone does not prove headline freshness.
        current_title = " ".join(EXPECTED["title"].split())
        current_url = f"https://{BRAND}.com/editions/{DATE}.html"
        for href in shares:
            parts = urlsplit(href)
            q = parse_qs(parts.query)
            if parts.scheme == "mailto" and not q.get("subject", [""])[0].startswith("You should read"):
                self.assertEqual(" ".join(q["subject"][0].split()), current_title)
                if BRAND == "factsfirstdaily":
                    self.assertEqual(q["subject"], [current_title])
            if parts.hostname == "twitter.com":
                self.assertEqual(" ".join(q["text"][0].split()), current_title)
                if BRAND == "factsfirstdaily":
                    self.assertEqual(q["text"], [current_title])
            if parts.hostname == "wa.me":
                self.assertEqual(" ".join(q["text"][0].split()), current_title + " " + current_url)
                if BRAND == "factsfirstdaily":
                    self.assertEqual(q["text"], [current_title + " " + current_url])
        for article in EXPECTED["stories"] + [EXPECTED["deep_dive"]]:
            for body in article["paragraphs"]:
                for a in BeautifulSoup(body, "html.parser").select("a[href]"):
                    self.assertIsNotNone(new.find("a", href=a["href"]))

    def test_original_regression_files_only_approved_fixture_edits(self):
        paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASE_COMMIT, "tests/"], cwd=ROOT, text=True).splitlines()
        for path in paths:
            expected = subprocess.check_output(["git", "show", f"{BASE_COMMIT}:{path}"], cwd=ROOT).decode()
            for before, after in FIXTURE_EDITS[BRAND].get(path, []):
                self.assertEqual(expected.count(before), 1, (path, "approved fixture patch must bind uniquely"))
                expected = expected.replace(before, after, 1)
            self.assertEqual((ROOT / path).read_text(), expected,
                             (path, "Original functional tests must differ ONLY by the exact approved fixture patch"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

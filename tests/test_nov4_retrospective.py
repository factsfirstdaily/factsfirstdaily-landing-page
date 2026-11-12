"""Retrospective Nov4 gap repair invariants. Never makes external requests."""
import hashlib
import json
import re
import subprocess
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=json.loads((ROOT/"tests/nov4_retrospective_expected.json").read_text())
CONTENT=FIXTURE["content"]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def soup(path):
    return BeautifulSoup((ROOT/path).read_text(),"html.parser")

def configuration(raw):
    match=re.search(r"const SITE_CONFIG\s*=\s*(\{.*?\});",raw,re.S)
    return json.loads(subprocess.check_output(["node","-e","process.stdout.write(JSON.stringify(("+match[1]+")))"],text=True))

class RetrospectiveRepair(unittest.TestCase):
    def test_01_all_existing_production_bytes_preserved_except_archive_card(self):
        for name,expected in FIXTURE["baseline"].items():
            if name.startswith("tests/"):continue
            raw=(ROOT/name).read_bytes()
            if name in ("index.html","editions/index.html"):
                insertion=FIXTURE["archive_insertion"].encode()
                self.assertEqual(raw.count(insertion),1)
                raw=raw.replace(insertion,b"",1)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),expected,name)
        self.assertEqual(digest(ROOT/"editions/2026-11-04.html"),FIXTURE["html_sha256"])

    def test_02_complete_sorted_archive_and_latest_unchanged(self):
        for name in ("index.html","editions/index.html"):
            config=configuration((ROOT/name).read_text())
            dates=[e["date"] for e in config["editions"]]
            self.assertEqual(dates,[f"2026-11-{day:02d}" for day in range(12,0,-1)])
            self.assertEqual(len(set(e["url"] for e in config["editions"])),12)
            self.assertEqual(config["editions"][0]["date"],"2026-11-12")
            self.assertIn("validEditions.forEach", (ROOT/name).read_text())

    def test_03_notice_dates_shares_and_navigation(self):
        doc=soup("editions/2026-11-04.html")
        self.assertEqual(doc.select_one("[data-retrospective]").get_text(),CONTENT["notice"])
        self.assertIn(CONTENT["cutoff_explanation"],doc.get_text())
        self.assertIn("Wednesday, November 4, 2026",doc.select_one(".eyebrow").get_text())
        self.assertIn("November 4, 2026",doc.title.get_text())
        self.assertEqual(doc.select_one('link[rel="canonical"]')["href"],"https://factsfirstdaily.com/editions/2026-11-04.html")
        for meta in doc.select('meta[property="og:url"]'):
            self.assertEqual(meta["content"],"https://factsfirstdaily.com/editions/2026-11-04.html")
        self.assertEqual([a["href"] for a in doc.select("nav.nav a")],["2026-11-03.html","2026-11-05.html","/#editions"])
        for anchor in doc.select(".share a[href]"):
            values=" ".join(v for rows in parse_qs(urlsplit(anchor["href"]).query).values() for v in rows)
            self.assertIn("https://factsfirstdaily.com/editions/2026-11-04.html",values)
            self.assertNotIn("2026-11-12.html",values)
        self.assertFalse(doc.select("main h1"))

    def test_04_full_original_slot_counts_and_exact_copy(self):
        doc=soup("editions/2026-11-04.html")
        self.assertEqual(len(doc.select("article.story")),4)
        for node,expected in zip(doc.select("article.story"),CONTENT["stories"]):
            self.assertEqual(node.h3.get_text(),expected["title"])
            paragraphs=node.find_all("p",recursive=False)
            self.assertEqual(len(paragraphs),4)
            self.assertEqual([p.get_text(" ",strip=True) for p in paragraphs],
              [BeautifulSoup(p,"html.parser").get_text(" ",strip=True) for p in expected["paragraphs"]])
        self.assertEqual(len(doc.select("#deep-dive .in p.body")),4)
        self.assertEqual(len(doc.select("p.brief")),12)
        self.assertEqual(len(doc.select("article.story img,#deep-dive img")),5)

    def test_05_real_sources_and_historical_cutoff(self):
        audit=FIXTURE["historical_evidence"]
        self.assertEqual(audit["status"],"PASS")
        self.assertEqual(audit["source_count"],16)
        cutoff=datetime.fromisoformat(audit["cutoff"])
        for record in audit["records"]:
            self.assertTrue(record["historically_eligible"])
            self.assertGreater(record["body_characters"],500)
            self.assertGreater(datetime.fromisoformat(record["opened_at"]),cutoff)
            modified=record["modified_timestamp_raw"]
            modified=datetime.fromisoformat(modified.replace("Z","+00:00"))
            if modified.tzinfo is None:modified=modified.replace(tzinfo=cutoff.tzinfo)
            self.assertLessEqual(modified,cutoff)
            self.assertIn(urlsplit(record["url"]).hostname,("apnews.com","www.theguardian.com"))

    def test_06_photos_no_duplicates_and_trivia_poll(self):
        doc=soup("editions/2026-11-04.html")
        photos=doc.select("article.story img,#deep-dive img")
        self.assertEqual(len({p["src"].split("?")[0] for p in photos}),5)
        self.assertTrue(all(urlsplit(p["src"]).hostname=="images.unsplash.com" for p in photos))
        self.assertTrue(all(p["alt"] and len(p["alt"].split())<15 for p in photos))
        for row in FIXTURE["historical_evidence"]["photos"]:
            if row["name"]=="photo-license":continue
            self.assertEqual(row["prior_same_brand_live_reuse"],[])
            self.assertIn("ACTUALLY_INSPECTED",row["visual_inspection"])
        trivia=doc.select_one("#tri")
        self.assertEqual(trivia["data-answer"],"2")
        self.assertEqual(len(trivia.select(".qz-opt")),4)
        self.assertIn(CONTENT["trivia"]["question"],trivia.get_text())
        for anchor in doc.select(".poll a[href]"):
            query=parse_qs(urlsplit(anchor["href"]).query)
            self.assertEqual(query["poll"],[CONTENT["poll"]["slug"]])
            self.assertIn(query["vote"][0],("yes","no"))
        self.assertIn("Current reader opinion",doc.select_one(".poll").get_text())

    def test_07_scripts_styles_header_footer_and_signup_unchanged(self):
        current=soup("editions/2026-11-04.html")
        baseline=soup("editions/2026-11-12.html")
        # A current-edition share payload is a date slot, not a footer redesign.
        for anchor in current.select("footer a[href]"):
            if anchor["href"].startswith("mailto:") and "2026-11-04.html" in anchor["href"]:
                anchor["href"]=anchor["href"].replace("2026-11-04.html","2026-11-12.html")
        for selector in ("script","style","link[rel=stylesheet]","header","footer"):
            self.assertEqual([str(n) for n in current.select(selector)],[str(n) for n in baseline.select(selector)],selector)
        self.assertEqual(digest(ROOT/"email/polls.js"),FIXTURE["baseline"]["email/polls.js"])
        for name in ("index.html","editions/index.html"):
            self.assertEqual(configuration((ROOT/name).read_text())["mailerliteFormAction"],
              "https://assets.mailerlite.com/jsonp/2756267/forms/203044673267173156/subscribe")

if __name__=="__main__":
    unittest.main(verbosity=2)

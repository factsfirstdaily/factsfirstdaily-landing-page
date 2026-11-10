from pathlib import Path
import json,hashlib,unittest
from bs4 import BeautifulSoup
from urllib.parse import urlsplit,parse_qs
R=Path(__file__).resolve().parents[1];E=json.loads((R/"tests/nov10_cpi_revision.json").read_text());C=json.loads((R/"tests/nov10_expected.json").read_text())["content"]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class CPIRevision(unittest.TestCase):
 def test_exact_bounded_revision_preserves_all_other_files(self):
  now={str(p.relative_to(R)):sha(p) for p in R.rglob("*") if p.is_file() and not any(x in p.parts for x in (".git","__pycache__"))}
  self.assertTrue(set(E["baseline"])<=set(now))
  self.assertEqual({n for n,d in now.items() if E["baseline"].get(n)!=d},set(E["allowed"]))
  for n,v in E["web_changes"].items():self.assertEqual(now[n],v["after_sha256"])
 def test_primary_actuals_and_no_stale_forecast(self):
  raw=(R/"editions/2026-11-10.html").read_text();s=BeautifulSoup(raw,"html.parser");text=s.get_text(" ",strip=True)
  self.assertIn("0.4%",text);self.assertIsNotNone(s.find("a",href=E["source"]))
  self.assertNotIn("Inflation data arrive Tuesday.",text)
  if E["brand"]=="factsfirstdaily":
   story=s.select_one("article.story");txt=story.get_text(" ",strip=True)
   self.assertIn("Both monthly figures are seasonally adjusted.",txt)
   self.assertIn("BLS did not publish annual headline or core rates",txt)
   self.assertIn("one governor’s view, not a new Fed decision",txt)
   self.assertNotIn("economists expect prices",txt);self.assertNotIn("stock futures were little changed",txt)
   self.assertEqual(len(story.select("p")),4)
   for a in s.select("a[href]"):
    u=urlsplit(a["href"]);q=parse_qs(u.query)
    if u.hostname in ("twitter.com","wa.me") or (u.scheme=="mailto" and q.get("subject",[""])[0].startswith("October")):
     flat=" ".join(v for a in q.values() for v in a);self.assertIn("October Prices Rise 0.4%.",flat);self.assertNotIn("Waller Backs a December Rate Hike.",flat)
  else:
   self.assertIn("GLP-1",text);self.assertIn("person-years",text);self.assertNotIn("GLP 1",text)
 def test_no_poll_or_immutable_source_changes(self):
  self.assertFalse(E["poll_changes"]);self.assertFalse(E["esp_writes"]);self.assertTrue(E["immutable_build_unchanged"])
if __name__=="__main__":unittest.main(verbosity=2)

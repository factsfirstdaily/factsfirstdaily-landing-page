"""Nov12 current-baseline release invariants. Never sends votes or signups."""
from pathlib import Path
import hashlib,json,re,subprocess,unittest
from urllib.parse import urljoin,urlsplit,parse_qs,unquote
from bs4 import BeautifulSoup
R=Path(__file__).resolve().parents[1]
E=json.loads((R/"tests/nov12_expected.json").read_text());C=E["content"]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def soup(p):return BeautifulSoup((R/p).read_text(),"html.parser")
def config(raw):
 m=re.search(r"const SITE_CONFIG\s*=\s*(\{.*?\});",raw,re.S);assert m
 return json.loads(subprocess.check_output(["node","-e","process.stdout.write(JSON.stringify(("+m[1]+")))"],text=True))
class Nov12(unittest.TestCase):
 def test_scope_and_history(self):
  allowed={"index.html","editions/index.html","editions/2026-11-11.html",
   "editions/2026-11-12.html","tests/nov12_expected.json","tests/test_nov12_site.py",
   "tests/interactions.test.cjs","tests/links_test.py","tests/nov12_source_audit.json"}
  now={str(p.relative_to(R)):sha(p) for p in R.rglob("*") if p.is_file() and not any(x in p.parts for x in (".git","__pycache__"))}
  self.assertTrue(set(E["baseline"])<=set(now))
  self.assertEqual({n for n,d in now.items() if E["baseline"].get(n)!=d},allowed)
  old=soup("editions/2026-11-11.html");nav=old.select_one("nav.nav")
  self.assertIsNotNone(nav.find("a",href="2026-11-12.html"))
  # The prior edition changes navigation only; exact raw editorial bytes pinned.
  raw=(R/"editions/2026-11-11.html").read_text()
  nav_raw=str(nav);nav.find("a",href="2026-11-12.html").decompose()
  restored=raw.replace(nav_raw,str(nav))
  self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),E["baseline"]["editions/2026-11-11.html"])
 def test_frozen_editorial_and_links(self):
  expected=BeautifulSoup(E["frozen"],"html.parser")
  expected.select_one("nav.nav a")["href"]="2026-11-11.html"
  for a in expected.select("footer a[href]"):
   if a.get_text(" ",strip=True) in ("Latest edition","Today's edition","Today's trivia","Daily trivia"):
    a["href"]=a["href"].replace("2026-11-11","2026-11-12")
  current=soup("editions/2026-11-12.html")
  self.assertEqual(str(current),str(expected))
  self.assertEqual(current.select_one("nav.nav a")["href"],"2026-11-11.html")
  self.assertEqual(current.select_one('meta[name="description"]')["content"],C["description"])
  self.assertEqual([x.h3.get_text(" ",strip=True) for x in current.select("article.story")],[x["title"] for x in C["stories"]])
  self.assertIn("November 12, 2026",current.get_text(" ",strip=True))
 def test_home_archive_exact_preservation(self):
  for rel in ("index.html","editions/index.html"):
   raw=(R/rel).read_text();cfg=config(raw)
   self.assertEqual(len(cfg["editions"]),11)
   self.assertEqual(cfg["editions"][0]["date"],"2026-11-12")
   self.assertEqual(cfg["editions"][0]["title"],C["title"])
   self.assertEqual(cfg["editions"][0]["description"],C["description"])
   self.assertEqual(cfg["editions"][0]["image"],soup("editions/2026-11-12.html").select_one("article.story img")["src"])
   # Strip only the inserted data card and known latest-link update; then
   # every original byte (signup, legal, footer, scripts, history) must match.
   m=re.search(r"const SITE_CONFIG\s*=\s*(\{.*?\});",raw,re.S)
   pos=raw.index("[",m.start(1)+m[1].index("editions"))
   card=json.dumps(cfg["editions"][0],ensure_ascii=False)
   self.assertTrue(raw[pos+1:].startswith(card+","))
   restored=raw[:pos+1]+raw[pos+1+len(card)+1:]
   # Link replacements serialize unchanged tags; only this date is advanced.
   for a in BeautifulSoup(restored,"html.parser").select("a[href]"):
    if "2026-11-12" in a["href"]:
     old=str(a);a["href"]=a["href"].replace("2026-11-12","2026-11-11")
     restored=restored.replace(old,str(a))
   self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),E["baseline"][rel])
   self.assertIn("validEditions.forEach(e => {",raw)
   self.assertNotIn("validEditions.slice(0,6)",raw)
 def test_real_poll_and_trivia(self):
  doc=soup("editions/2026-11-12.html")
  poll=doc.select_one(".poll")
  self.assertIn(C["poll"]["question"],poll.get_text(" ",strip=True))
  self.assertEqual(len(poll.select("a[href]")),2)
  for a in poll.select("a[href]"):
   q=parse_qs(urlsplit(a["href"]).query)
   self.assertEqual(q["poll"],[C["poll"]["slug"]])
   self.assertIn(q["vote"][0],("yes","no"))
  self.assertEqual(sha(R/"email/polls.js"),E["baseline"]["email/polls.js"])
  self.assertIn("https://", (R/"email/polls.js").read_text())
  tri=doc.select_one("#tri")
  self.assertIn(C["trivia"]["question"],tri.get_text(" ",strip=True))
  self.assertEqual(tri["data-answer"],str("ABCD".index(C["trivia"]["correct_letter"])))
 def test_all_internal_links_and_syntax(self):
  pages={p.resolve():BeautifulSoup(p.read_text(),"html.parser") for p in R.rglob("*.html")}
  for p,doc in pages.items():
   for a in doc.select("[href],[src]"):
    raw=a.get("href",a.get("src",""))
    if raw=="{!remove_web}":continue
    u=urlsplit(urljoin("https://factsfirstdaily.com/"+p.relative_to(R).as_posix(),raw))
    if u.hostname!="factsfirstdaily.com" or u.scheme!="https":continue
    target=R/unquote(u.path).lstrip("/")
    if target.is_dir():target/="index.html"
    self.assertTrue(target.is_file(),(p,raw))
    if u.fragment and target.resolve() in pages:self.assertIsNotNone(pages[target.resolve()].find(id=unquote(u.fragment)),(p,raw))
   for script in doc.select("script:not([src])"):
    result=subprocess.run(["node","--check"],input=script.get_text(),capture_output=True,text=True)
    self.assertEqual(result.returncode,0,(p,result.stderr))

class Nov12SourcePolicy(unittest.TestCase):
 def test_all_final_reporting_sources_exactly_audited(self):
  audit=json.loads((R/"tests/nov12_source_audit.json").read_text())
  self.assertEqual(sha(R/"tests/nov12_source_audit.json"),E["source_audit_sha256"])
  self.assertEqual(audit["status"],"PASS");self.assertFalse(audit["unapproved_final_urls"])
  chunks=[]
  for row in C["stories"]+[C["deep_dive"]]:chunks.extend(row["paragraphs"])
  for rows in C["briefing"].values():chunks.extend(rows)
  chunks.append(C["trivia"]["explanation"])
  urls={a["href"] for a in BeautifulSoup(" ".join(chunks),"html.parser").select("a[href]")}
  records={row["url"]:row for row in audit["records"]}
  self.assertEqual(urls,set(records));self.assertEqual(len(urls),23)
  direct=wire=0
  for row in records.values():
   self.assertEqual(row["status"],200);self.assertGreater(row["body_characters"],500)
   self.assertTrue(row["reader_citation_slots"])
   for key in ("evidence","raw_evidence"):self.assertRegex(row[key]["sha256"],r"^[a-f0-9]{64}$")
   if row["classification"]=="FULL_WIRE_SYNDICATION_EXPLICITLY_VERIFIED":
    wire+=1;self.assertIn(row["approved_original_publisher"],("Reuters","Bloomberg","AP"));self.assertTrue(row["syndication_proof_exact_quotes"])
   else:
    direct+=1;self.assertEqual(row["classification"],"DIRECT_APPROVED_OUTLET")
  self.assertEqual((direct,wire),(17,6))
 def test_fresh_corrections_and_unchanged_poll(self):
  doc=soup("editions/2026-11-12.html");text=doc.get_text(" ",strip=True)
  self.assertIn("eight people dead and 17 hurt",text);self.assertIn("7:36 a.m. ET",text)
  self.assertIn("10th in-person meeting",text)
  self.assertEqual(C["poll"],{"question":"Should Nvidia's board replace Jensen Huang as CEO?","slug":"nov12-2026-nvidia-huang-ceo"})

if __name__=="__main__":unittest.main(verbosity=2)

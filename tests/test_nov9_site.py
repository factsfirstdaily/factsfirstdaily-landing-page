"""Nov9 release-candidate regression checks. No requests, votes or signups."""
from pathlib import Path
import hashlib, json, re, subprocess, unittest
from urllib.parse import urljoin,urlsplit,unquote,parse_qs
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
E=json.loads((ROOT/"tests/nov9_expected.json").read_text())
B=E["brand"];C=E["content"];DATE=E["date"];OLD=E["old"]
def soup(p,base=ROOT):return BeautifulSoup((base/p).read_text(),"html.parser")
def norm(s):return " ".join(s.split())
def config(p,base=ROOT):
 raw=(base/p).read_text();m=re.search(r"(?:const|var) SITE_CONFIG\s*=\s*(\{.*?\});",raw,re.S);assert m
 return json.loads(subprocess.check_output(["node","-e","process.stdout.write(JSON.stringify(("+m[1]+")))"],text=True))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def locked(doc):
 scripts=[]
 for n in doc.select("script"):
  raw=n.get_text()
  if "SITE_CONFIG" in raw:
   m=re.search(r"(?:const|var) SITE_CONFIG\s*=\s*(\{.*?\});",raw,re.S)
   scripts.append(h(raw[:m.start(1)]+"<EDITION_DATA>"+raw[m.end(1):]))
  else:scripts.append(h(str(n)))
 return {"style":[h(str(n)) for n in doc.select("style,link[rel=stylesheet]")],
         "header":[h(str(n)) for n in doc.select("header")],
         "form":[h(str(n)) for n in doc.select("form")],"scripts":scripts,
         "topics":h(str(doc.select_one(".topics"))),
         "route_nov9":h(str(doc.select_one(".route")))}
class Nov9Candidate(unittest.TestCase):
 def test_01_changed_scope_and_fixed_files(self):
  allowed={"index.html",f"editions/{DATE}.html",f"editions/{OLD}.html","tests/test_nov9_site.py","tests/nov9_expected.json"}
  if B=="factsfirstdaily":allowed.add("editions/index.html")
  if B=="worldskim":allowed.add("archive.html")
  allowed.update(E["fixture_file_sha256"])
  allowed.add("tests/nov9_fixture_edits.json")
  original=E["baseline"]["files"]
  current={str(p.relative_to(ROOT)):p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
  current={name:p for name,p in current.items() if ".git" not in p.parts}
  self.assertTrue(set(original)<=set(current))
  changed={p for p in current if p not in original or digest(current[p])!=original[p]}
  self.assertEqual(changed,allowed)
  for p in original:
   if p not in allowed:self.assertEqual(original[p],digest(current[p]),p)
  for p,d in E["fixture_file_sha256"].items():self.assertEqual(d,digest(ROOT/p),p)
  self.assertEqual(E["fixture_edits_sha256"],digest(ROOT/"tests/nov9_fixture_edits.json"))
 def test_02_historical_editorial_unchanged(self):
  for rel,d in E["baseline"]["files"].items():
   if not re.fullmatch(r"editions/\d{4}-\d{2}-\d{2}\.html",rel):continue
   if Path(rel).stem!=OLD:self.assertEqual(d,digest(ROOT/rel),rel);continue
   b=soup(rel)
   b.select_one("nav.nav,nav.ednav,nav.ed-nav").decompose()
   self.assertEqual(E["baseline"]["nov8_without_nav_sha256"],h(str(b)))
 def test_03_new_page_only_approved_navigation_diff(self):
  current=soup(f"editions/{DATE}.html")
  for doc in (current,):
   doc.select_one("nav.nav,nav.ednav,nav.ed-nav").decompose()
   for a in doc.select("footer a[href]"):
    if a.get_text(" ",strip=True) in ("Latest edition","Today's edition","Today's trivia","Daily trivia"):
     a["href"]=a["href"].replace(OLD,DATE)
  self.assertEqual(E["baseline"]["frozen_nov9_normalized_sha256"],h(str(current)))
 def test_04_archive_metadata_and_exact_history(self):
  paths=["index.html"]+(["archive.html"] if B=="worldskim" else ["editions/index.html"] if B=="factsfirstdaily" else [])
  for p in paths:
   current=config(p);old=E["baseline"]["homes"][p]["config"];a=current["editions"].pop(0)
   self.assertEqual(current,old)
   self.assertEqual(a["url"].split("/")[-1],DATE+".html")
   self.assertEqual(norm("\n".join(a["title"]) if isinstance(a["title"],list) else a["title"]),norm(C["title"]))
   self.assertEqual(a["description"],C["description"])
   self.assertEqual(a["image"],E["baseline"]["frozen_first_image"])
   self.assertEqual(a["date"],DATE if B=="factsfirstdaily" else "Mon, Nov 9" if B=="thedailyskim" else "Monday, November 9, 2026")
 def test_05_navigation_and_current_meta(self):
  doc=soup(f"editions/{DATE}.html")
  nav=doc.select_one("nav.nav,nav.ednav,nav.ed-nav")
  self.assertEqual(nav.find("a")["href"],OLD+".html")
  self.assertIsNotNone(soup(f"editions/{OLD}.html").select_one(f'nav a[href="{DATE}.html"]'))
  self.assertEqual(norm(doc.title.get_text()),norm(C["title"]))
  self.assertEqual(doc.select_one('meta[name="description"]')["content"],C["description"])
  self.assertIn("November 9, 2026",doc.get_text(" ",strip=True))
  for a in doc.select("footer a[href]"):
   if a.get_text(" ",strip=True) in ("Latest edition","Today's edition","Today's trivia","Daily trivia"):
    self.assertIn(DATE,a["href"])
 def test_06_exact_news_photos_sources(self):
  doc=soup(f"editions/{DATE}.html")
  self.assertEqual([x.h3.get_text(" ",strip=True) for x in doc.select("article.story")],[x["title"] for x in C["stories"]])
  self.assertEqual(doc.select_one("#dd-h").get_text(" ",strip=True),C["deep_dive"]["title"])
  for node,a in zip(doc.select("article.story")+[doc.select_one("#deep-dive")],C["stories"]+[C["deep_dive"]]):
   visible=norm(node.get_text(" ",strip=True))
   image=node.find("img");self.assertIsNotNone(image)
   # Existing fixed web renderer uses q=80 while approved content stores q=85.
   # Bind every other URL component and the frozen rendered URL exactly.
   expected=a["photo"]["image_url"].replace("q=85","q=80")
   self.assertEqual(image["src"],expected)
   self.assertEqual(image["alt"],a["photo"]["alt"])
   # The fixed web templates show the approved alt/file-photo caption, not a
   # newly invented photo-credit link; complete frozen DOM equality is checked.
   self.assertTrue(a["photo"]["original_url"].startswith("https://unsplash.com/photos/"))
   for p in a["paragraphs"]:
    frag=BeautifulSoup(p,"html.parser");self.assertIn(norm(frag.get_text(" ",strip=True)),visible)
    for link in frag.select("a[href]"):self.assertIsNotNone(node.find("a",href=link["href"]))
 def test_07_native_poll_trivia_and_shares(self):
  doc=soup(f"editions/{DATE}.html");poll=doc.select_one(".poll,#reader-poll")
  self.assertIn(C["poll"]["question"],poll.get_text(" ",strip=True))
  for a in poll.select("a[href]"):
   q=parse_qs(urlsplit(a["href"]).query);self.assertEqual(q["poll"],[C["poll"]["slug"]])
   self.assertIn(q["vote"][0],("yes","no"))
  self.assertEqual(len(poll.select("a[href]")),2)
  tri=doc.select_one("#tri");self.assertIn(C["trivia"]["question"],tri.get_text(" ",strip=True))
  self.assertEqual(len(tri.select(".qz-opt")),4)
  self.assertEqual(tri["data-answer"],str("ABCD".index(C["trivia"]["correct_letter"])))
  for a in doc.select("a[href]"):
   href=a["href"]
   if any(x in href for x in ("mailto:?subject=","facebook.com/sharer/","twitter.com/intent/","threads.net/intent/","linkedin.com/sharing/","reddit.com/submit","wa.me/?")):
    flat=" ".join(v for vals in parse_qs(urlsplit(href).query).values() for v in vals)
    self.assertIn(f"https://{B}.com/editions/{DATE}.html",flat)
    self.assertNotIn(OLD+".html",flat)
 def test_08_all_local_destinations_and_anchors(self):
  pages={p.resolve():BeautifulSoup(p.read_text(),"html.parser") for p in ROOT.rglob("*.html")}
  for p,doc in pages.items():
   for n in doc.select("[href],[src]"):
    raw=n.get("href",n.get("src",""))
    if p.parent.name=="email" and raw=="{!remove_web}":continue
    u=urlsplit(urljoin(f"https://{B}.com/"+p.relative_to(ROOT).as_posix(),raw))
    if u.hostname!=B+".com" or u.scheme!="https":continue
    target=ROOT/unquote(u.path).lstrip("/")
    if target.is_dir():target/="index.html"
    self.assertTrue(target.is_file(),(str(p.relative_to(ROOT)),raw))
    if u.fragment and target.resolve() in pages:self.assertIsNotNone(pages[target.resolve()].find(id=unquote(u.fragment)),(str(p),raw))
 def test_09_home_styles_brand_route_forms_legal(self):
  for name in ["index.html"]+(["archive.html"] if B=="worldskim" else ["editions/index.html"] if B=="factsfirstdaily" else []):
   b=soup(name);old=E["baseline"]["homes"][name]["locked"];current=locked(b)
   for key in ("style","header","form","scripts"):self.assertEqual(old[key],current[key],(name,key))
   if B=="worldskim" and name=="index.html":
    self.assertIsNotNone(b.select_one(".route"))
    self.assertIn("Your Six Minute Tour of the Planet",b.get_text())
    self.assertEqual(old["route_nov9"],current["route_nov9"])
   if B=="factsfirstdaily":
    self.assertEqual(old["topics"],current["topics"])
 def test_10_home_switcher_current_content(self):
  home=soup("index.html")
  if B=="thedailyskim":
   links=home.select(".sw-item");self.assertEqual(len(links),5)
   self.assertEqual([a.get_text() for a in links],[a["title"] for a in C["stories"]+[C["deep_dive"]]])
   self.assertEqual(len(home.select(".sw-dots button")),5)
  elif B=="worldskim":
   items=json.loads(home.select_one(".switcher")["data-items"])
   self.assertEqual([x[0] for x in items],[a["title"] for a in C["stories"]])
   self.assertTrue(all(DATE in x[1] for x in items))
   first=home.select_one("#edition-grid article.card")
   self.assertEqual(first.select_one("a")["href"],f"editions/{DATE}.html")
   self.assertIn(C["description"],first.get_text(" ",strip=True))
  for a in home.select("a[href]"):
   if OLD in a["href"]:self.assertIsNotNone(a.find_parent(id="edition-grid"),str(a))
 def test_11_javascript_syntax(self):
  for p in ROOT.rglob("*.html"):
   for script in BeautifulSoup(p.read_text(),"html.parser").select("script:not([src])"):
    r=subprocess.run(["node","--check"],input=script.get_text(),text=True,capture_output=True)
    self.assertEqual(r.returncode,0,(str(p),r.stderr))
if __name__=="__main__":unittest.main(verbosity=2)

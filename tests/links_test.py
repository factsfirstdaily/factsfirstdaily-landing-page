"""Static internal-link and dated-content QA; never submits or follows poll URLs."""
import re
import html
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, parse_qs

ROOT = Path(".").resolve()
class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.ids, self.meta = [], set(), {}
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in ("a", "link") and "href" in a:
            self.links.append(a["href"])
        if tag in ("img", "script") and "src" in a:
            self.links.append(a["src"])
        if tag == "meta":
            self.meta[a.get("name", a.get("property", ""))] = a.get("content")

pages = {str(p.relative_to(ROOT)): Page(p.read_text()) for p in ROOT.rglob("*.html") if ".git" not in p.parts}
missing, checked = [], 0
for file, page in pages.items():
    for link in page.links:
        u = urlsplit(urljoin("https://factsfirstdaily.com/" + file, link))
        if u.scheme != "https" or u.hostname != "factsfirstdaily.com":
            continue
        path = u.path.lstrip("/")
        if not path or path.endswith("/"):
            path += "index.html"
        assert (ROOT / path).is_file(), (file, link, path)
        if u.fragment and path in pages:
            assert u.fragment in pages[path].ids, (file, link, "missing anchor")
        checked += 1
new = (ROOT / "editions/2026-11-06.html").read_text()
old = (ROOT / "editions/2026-11-05.html").read_text()
page = pages["editions/2026-11-06.html"]
assert 'href="2026-11-05.html">← Previous edition' in html.unescape(new)
assert 'href="2026-11-06.html">Next edition →' in html.unescape(old)
for tag in ("header", "footer", "script"):
    pattern = r"<" + tag + r"\b.*?</" + tag + ">"
    assert re.search(pattern, new, re.S)[0] == re.search(pattern, old, re.S)[0], ("Locked template changed", tag)
assert "<title>Facts First Daily</title>" in re.search(r"<header\b.*?</header>", new, re.S)[0]
for p in ROOT.glob("editions/2026-*.html"):
    expected_latest = "2026-11-12" if p.name == "2026-11-12.html" else "2026-11-11" if p.name == "2026-11-11.html" else "2026-11-10" if p.name == "2026-11-10.html" else "2026-11-09" if p.name == "2026-11-09.html" else "2026-11-08" if p.name == "2026-11-08.html" else "2026-11-07" if p.name == "2026-11-07.html" else "2026-11-06"
    assert f'href="/editions/{expected_latest}.html">Latest edition' in p.read_text()
assert page.meta["og:image"] == re.search(r'<img[^>]*src="([^"]+)"', new)[1].replace("&amp;", "&")
assert "Friday, November 6, 2026" in new
assert 'href="https://factsfirstdaily.com/editions/2026-11-06.html" rel="canonical"' in new or 'rel="canonical" href="https://factsfirstdaily.com/editions/2026-11-06.html"' in new
for link in page.links:
    u = urlsplit(link)
    if u.scheme == "mailto" and u.query:
        q = parse_qs(u.query)
        if "subject" in q and "body" in q and "2026-11-06" in q["body"][0]:
            assert "Raman" in q["subject"][0]
    if u.hostname in ("twitter.com", "wa.me"):
        assert "Raman" in parse_qs(u.query)["text"][0]
assert not missing
thanks = (ROOT / "email/thanks.html").read_text()
assert thanks == (ROOT / "editions/thanks.html").read_text()
assert 'src="/email/polls.js"' in thanks
assert 'id="poll-confirm" type="button" disabled' in thanks
assert "Thanks for voting!" not in thanks
assert "share the results in tomorrow" not in thanks
print(f"PASS: {checked} internal file/anchor references; previous/next/latest and fresh share metadata.")
print("PASS: both poll confirmation paths exist locally, share one loader and make no static success/results claim.")
print("Deployment and real collector integration remain unverified by this static test.")
print("NO poll votes, subscriptions, source article requests or other network requests performed.")

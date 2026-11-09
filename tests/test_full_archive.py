"""Nov9 pinned-base archive regression; no votes/signups/network writes.

Run: python tests/test_full_archive.py
Requires Playwright and its Chromium installation.
Production byte locks intentionally bind to the reviewed Nov9 main commit,
not a generic baseline for future editorial releases.
"""
import asyncio
import functools
import hashlib
import http.server
import subprocess
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "9a2fbac0b3a2259dc497440b9fff741a727230f0"
PAGES = ("index.html", "editions/index.html")
OLD = "  validEditions.slice(0,6).forEach(e => {"
NEW = "  validEditions.forEach(e => {"


def original(path):
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class FullArchive(unittest.TestCase):
    def test_exact_production_change_and_preserved_history(self):
        # Freeze every production byte, not just selected DOM/style hashes.
        paths = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", BASE], cwd=ROOT, text=True
        ).splitlines()
        for path in paths:
            if path.startswith("tests/"):
                continue
            before = original(path)
            current = (ROOT / path).read_bytes()
            if path in PAGES:
                self.assertEqual(before.count(OLD.encode()), 1, path)
                self.assertEqual(current.count(NEW.encode()), 1, path)
                self.assertEqual(current, before.replace(OLD.encode(), NEW.encode(), 1), path)
            else:
                self.assertEqual(hashlib.sha256(current).digest(),
                                 hashlib.sha256(before).digest(), path)

    def test_all_configured_urls_rendered_and_readable_desktop_mobile(self):
        asyncio.run(self.check_rendered())

    async def check_rendered(self):
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                for width in (1440, 390):
                    context = await browser.new_context(
                        viewport={"width": width, "height": 900}, service_workers="block")
                    writes = []

                    async def intercept(route):
                        req = route.request
                        if req.method not in ("GET", "HEAD"):
                            writes.append({"method": req.method, "url": req.url})
                            await route.abort()
                        elif req.url.startswith(origin + "/"):
                            await route.continue_()
                        else:
                            # No external reads or writes needed to validate cards.
                            await route.abort()

                    await context.route("**/*", intercept)
                    page = await context.new_page()
                    for path in PAGES:
                        response = await page.goto(origin + "/" + path)
                        self.assertEqual(response.status, 200)
                        await page.locator("#editions-grid:not([hidden])").wait_for()
                        configured = await page.evaluate(
                            "SITE_CONFIG.editions.map(e => ({url:e.url, date:e.date, title:e.title}))")
                        self.assertGreater(len(configured), 6)
                        cards = page.locator("#editions-grid > a.edition")
                        self.assertEqual(await cards.count(), len(configured), (path, width))
                        self.assertEqual(await cards.evaluate_all("(xs) => xs.map(x => x.href)"),
                                         [e["url"] for e in configured], (path, width))
                        self.assertEqual(await cards.locator("time").evaluate_all(
                            "(xs) => xs.map(x => x.dateTime)"),
                            [e["date"] for e in configured])
                        for i, edition in enumerate(configured):
                            card = cards.nth(i)
                            await card.scroll_into_view_if_needed()
                            self.assertTrue(await card.is_visible(), (path, width, edition["date"]))
                            self.assertEqual(await card.locator("h3").text_content(), edition["title"])
                            box = await card.bounding_box()
                            self.assertGreater(box["width"], 0)
                            self.assertGreater(box["height"], 0)
                        self.assertFalse(await page.locator("#editions-empty").is_visible())
                        self.assertGreater(await page.locator("[data-signup-form]").count(), 0)
                        self.assertLessEqual(await page.evaluate(
                            "document.documentElement.scrollWidth"), width)
                    # Follow actual rendered card destinations locally; no vote/signup clicks.
                    for edition in configured:
                        target = urlsplit(edition["url"])
                        self.assertEqual(target.hostname, "factsfirstdaily.com")
                        self.assertRegex(target.path, r"^/editions/\d{4}-\d{2}-\d{2}\.html$")
                        response = await page.goto(origin + target.path)
                        self.assertEqual(response.status, 200)
                        self.assertGreater(len(await page.locator("main").inner_text()), 1000)
                        self.assertTrue(await page.locator("article.story").first.is_visible())
                        self.assertIn("Facts First Daily", await page.locator("body").inner_text())
                    self.assertEqual(writes, [], "No writes allowed during archive browsing")
                    await context.close()
                await browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)

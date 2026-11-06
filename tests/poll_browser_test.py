"""Run with Playwright installed; serves originals locally and mocks ALL collector traffic.
No real vote endpoint, subscription or other external request is reached.
Example: /opt/coworker-deps/.venv/bin/python tests/poll_browser_test.py
"""
import asyncio
import functools
import http.server
import json
import re
import threading
import time
from pathlib import Path
from playwright.async_api import async_playwright

ENDPOINT = "https://energized-kiwi-650.convex.site/v1/votes"
SLUG = "los-angeles-housing-2026"
KEY = "ffd-poll-browser-v1"
OUT = Path("/tmp/ffd-poll-screenshots")

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

async def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(Path.cwd())))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    OUT.mkdir(exist_ok=True)
    checks = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        async def session(init=None, mobile=False):
            context = await browser.new_context(viewport={"width": 390 if mobile else 1100, "height": 844 if mobile else 850}, device_scale_factor=1)
            calls = []
            state = {"status": 200, "body": {"ok": True, "duplicate": False, "vote": "yes"}, "network_failure": False, "delay": None}
            async def route(reqroute):
                request = reqroute.request
                if request.url.startswith(base + "/"):
                    await reqroute.continue_()
                elif request.url == ENDPOINT:
                    if request.method == "OPTIONS":
                        await reqroute.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "POST"})
                        return
                    calls.append({"method": request.method, "body": request.post_data_json, "headers": request.headers})
                    assert request.method == "POST", "No GET vote writes"
                    if state["delay"]:
                        await state["delay"].wait()
                    if state["network_failure"]:
                        await reqroute.abort("failed")
                    else:
                        await reqroute.fulfill(status=state["status"], content_type="application/json", body=json.dumps(state["body"]), headers={"Access-Control-Allow-Origin": "*"})
                else:
                    raise AssertionError("Unexpected external request: " + request.url)
            await context.route("**/*", route)
            if init:
                await context.add_init_script(init)
            return context, await context.new_page(), calls, state
        async def open_poll(page, query=f"?poll={SLUG}&vote=yes", path="/email/thanks.html"):
            response = await page.goto(base + path + query)
            assert response.status == 200
            await page.wait_for_load_state("networkidle")
        async def status(page):
            return await page.locator("#poll-status").inner_text()

        # Served original files at both public paths. Visiting and reloading never writes.
        context, page, calls, state = await session()
        await open_poll(page)
        assert calls == [] and await page.locator("#poll-confirm").is_enabled()
        assert "You selected Yes" in await status(page)
        assert await page.evaluate(f"localStorage.getItem('{KEY}')") is None
        await page.screenshot(path=str(OUT / "confirm-desktop.png"), full_page=True)
        await page.reload()
        await page.wait_for_load_state("networkidle")
        assert calls == []
        # Programmatic click is not an explicit trusted click.
        await page.locator("#poll-confirm").evaluate("(el) => el.click()")
        assert calls == []
        await page.locator("#poll-confirm").click()
        await page.get_by_role("heading", name="Vote recorded", exact=True).wait_for()
        assert len(calls) == 1
        payload = calls[0]["body"]
        assert set(payload) == {"brand", "poll", "vote", "voter"}
        assert payload["brand"] == "factsfirstdaily" and payload["poll"] == SLUG and payload["vote"] == "yes"
        assert re.fullmatch("[a-f0-9]{32}", payload["voter"])
        assert "referer" not in calls[0]["headers"] and "cookie" not in calls[0]["headers"]
        record = json.loads(await page.evaluate(f"localStorage.getItem('{KEY}')"))
        assert record["voter"] == payload["voter"]
        assert 29.99 * 86400000 < record["expiresAt"] - time.time()*1000 <= 30 * 86400000
        assert "Your Yes vote was recorded." == await status(page)
        assert await page.locator("#poll-confirm").is_disabled()
        await page.screenshot(path=str(OUT / "success-desktop.png"), full_page=True)
        checks += 1

        # Same browser token, immutable original Yes choice despite a later No link.
        state["body"] = {"ok": True, "duplicate": True, "vote": "yes"}
        await open_poll(page, f"?poll={SLUG}&vote=no", "/editions/thanks.html")
        assert len(calls) == 1 and "You selected No" in await status(page)
        await page.locator("#poll-confirm").click()
        await page.get_by_role("heading", name="Vote already recorded", exact=True).wait_for()
        assert len(calls) == 2 and calls[1]["body"]["voter"] == payload["voter"]
        assert calls[1]["body"]["vote"] == "no"
        assert "recorded Yes vote" in await status(page) and "original choice was kept" in await status(page)
        await page.screenshot(path=str(OUT / "duplicate-desktop.png"), full_page=True)
        await context.close()
        checks += 1

        # Invalid and missing URL input fails closed before enabling confirmation.
        for query in ["", "?poll=x", "?vote=yes", "?poll=x&vote=", "?poll=x&vote=YES", "?poll=bad%20slug&vote=yes", "?poll=x&vote=yes&vote=no", "?poll=x&poll=y&vote=yes"]:
            context, page, calls, state = await session()
            await open_poll(page, query)
            assert await page.locator("#poll-confirm").is_disabled()
            assert "missing or invalid" in await status(page) and calls == []
            await context.close()
            checks += 1

        # API rejections, unverified/contradictory responses and network errors never show success.
        failures = [
            (404, {"error": "Unknown poll", "code": "UNKNOWN_POLL"}, False),
            (409, {"error": "Closed poll", "code": "POLL_CLOSED"}, False),
            (400, {"error": "Invalid", "code": "INVALID_INPUT"}, False),
            (500, {"ok": True, "duplicate": False, "vote": "yes"}, False),
            (200, {"ok": False, "duplicate": False, "vote": "yes"}, False),
            (200, {"ok": True, "vote": "yes"}, False),
            (200, {"ok": True, "duplicate": False, "vote": "no"}, False),
            (200, {"ok": True, "duplicate": True, "vote": "invalid"}, False),
            (200, None, True),
        ]
        for code, body, network_failure in failures:
            context, page, calls, state = await session()
            state.update(status=code, body=body, network_failure=network_failure)
            await open_poll(page)
            await page.locator("#poll-confirm").click()
            await page.get_by_text("We could not verify your vote.", exact=False).wait_for()
            assert await page.locator("#poll-confirm").is_enabled()
            assert await page.locator("#poll-heading").inner_text() == "Confirm your vote"
            assert len(calls) == 1
            if code == 404:
                await page.screenshot(path=str(OUT / "collector-error-desktop.png"), full_page=True)
            # Retry is explicit and uses the same persisted token.
            first = calls[0]["body"]["voter"]
            state.update(status=200, body={"ok": True, "duplicate": True, "vote": "yes"}, network_failure=False)
            await page.locator("#poll-confirm").click()
            await page.get_by_role("heading", name="Vote already recorded", exact=True).wait_for()
            assert len(calls) == 2 and calls[1]["body"]["voter"] == first
            await context.close()
            checks += 1

        # Authoritative collector error contract has no code field. Deterministic
        # closed/unavailable states stop, rather than encourage endless retries.
        for code, error, heading in [
            (409, "poll_closed", "Poll closed"),
            (404, "unknown_poll", "Poll unavailable"),
            (503, "voting_disabled", "Voting unavailable"),
            (429, "poll_capacity_reached", "Poll unavailable"),
        ]:
            context, page, calls, state = await session()
            state.update(status=code, body={"ok": False, "error": error})
            await open_poll(page)
            await page.locator("#poll-confirm").click()
            await page.get_by_role("heading", name=heading, exact=True).wait_for()
            assert "No vote was recorded." in await status(page)
            assert await page.locator("#poll-confirm").is_disabled()
            assert len(calls) == 1
            await page.locator("#poll-confirm").evaluate("(el) => el.click()")
            assert len(calls) == 1
            if error in ("poll_closed", "unknown_poll"):
                await page.screenshot(path=str(OUT / (error + "-desktop.png")), full_page=True)
            await context.close()
            checks += 1

        # Pending request plus rapid repeat clicks cannot produce more than one POST.
        context, page, calls, state = await session()
        state["delay"] = asyncio.Event()
        await open_poll(page)
        await page.locator("#poll-confirm").click()
        await page.wait_for_function("document.querySelector('#poll-confirm').disabled")
        await page.mouse.click(*(await page.locator("#poll-confirm").evaluate("(e)=>{let r=e.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}")))
        assert len(calls) == 1
        state["delay"].set()
        await page.get_by_role("heading", name="Vote recorded", exact=True).wait_for()
        await context.close()
        checks += 1

        # Blocked storage stops before POST, including repeated user retries.
        for blocked in ["Object.defineProperty(window, 'localStorage', {get(){throw Error('blocked')}})", "Storage.prototype.setItem=function(){throw Error('blocked writes')}"]:
            context, page, calls, state = await session(blocked)
            await open_poll(page)
            await page.locator("#poll-confirm").click()
            assert "Browser storage is unavailable" in await status(page)
            await page.locator("#poll-confirm").click()
            assert calls == [] and await page.locator("#poll-confirm").is_enabled()
            await page.screenshot(path=str(OUT / "storage-error-desktop.png"), full_page=True)
            await context.close()
            checks += 1

        for script in ["Object.defineProperty(window.crypto, 'getRandomValues', {value:undefined})", "window.fetch=undefined"]:
            context, page, calls, state = await session(script)
            await open_poll(page)
            assert "cannot securely confirm" in await status(page)
            assert await page.locator("#poll-confirm").is_disabled() and calls == []
            await context.close()
            checks += 1

        # Expired token is replaced only after trusted confirmation; no onload refresh.
        expired = {"voter": "a"*32, "expiresAt": int(time.time()*1000)-1000}
        context, page, calls, state = await session(f"localStorage.setItem('{KEY}', {json.dumps(json.dumps(expired))})")
        await open_poll(page)
        assert json.loads(await page.evaluate(f"localStorage.getItem('{KEY}')")) == expired and calls == []
        await page.locator("#poll-confirm").click()
        await page.get_by_role("heading", name="Vote recorded", exact=True).wait_for()
        assert calls[0]["body"]["voter"] != expired["voter"]
        await context.close()
        checks += 1

        context, page, calls, state = await session(mobile=True)
        await open_poll(page, f"?poll={SLUG}&vote=no")
        await page.screenshot(path=str(OUT / "confirm-mobile.png"), full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert calls == []
        await open_poll(page, "")
        await page.screenshot(path=str(OUT / "invalid-mobile.png"), full_page=True)
        await context.close()
        checks += 1
        await browser.close()
    server.shutdown()
    server.server_close()
    print(f"PASS: {checks} local-browser poll scenarios. Collector entirely mocked; zero external requests/votes.")
    print(f"Screenshots: {OUT}")

if __name__ == "__main__":
    asyncio.run(main())

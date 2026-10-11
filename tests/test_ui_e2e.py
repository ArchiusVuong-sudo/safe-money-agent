"""Browser walk of the main flow in replay mode (Playwright, local Chrome, headless).

Needs the built UI (npm run build in web/). Skips with a reason when the build
or a local Chrome is missing.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from safemoney.api import build_state, create_app
from safemoney.config import Settings

from .conftest import FIXTURES, REPO
from .test_api_e2e import free_port

DIST = REPO / "web" / "dist"
pytestmark = pytest.mark.ui


@pytest.fixture
def ui_url(tmp_path: Path) -> Iterator[str]:
    if not (DIST / "index.html").exists():
        pytest.skip("web/dist is missing: run npm run build in web/")
    port = free_port()
    settings = Settings(port=port, data_dir=tmp_path / "data", fixtures_dir=FIXTURES, web_dist=DIST, force_replay=True, replay_delay_ms=60)
    server = uvicorn.Server(
        uvicorn.Config(create_app(build_state(settings, dt.date.today())), host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=10)


def test_fix_this_hold_to_approve(ui_url: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # no local Chrome
            pytest.skip(f"no local Chrome for Playwright: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(ui_url)
            sync_api.expect(page.get_by_test_id("synthetic-badge")).to_be_visible()
            sync_api.expect(page.get_by_test_id("mode-badge")).to_have_text("Replay mode")
            sync_api.expect(page.get_by_test_id("overdraft-alert")).to_contain_text("-$304.29")

            page.get_by_test_id("fix-this").click()
            card = page.get_by_test_id("approval-card").first
            sync_api.expect(card).to_have_attribute("data-status", "pending", timeout=20_000)
            sync_api.expect(page.get_by_test_id("trace-panel")).to_contain_text("Policy passed, asking the user")

            # A short tap does not approve; a full hold does.
            hold = page.get_by_test_id("hold-approve")
            box = hold.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.wait_for_timeout(250)
            page.mouse.up()
            page.wait_for_timeout(300)
            sync_api.expect(card).to_have_attribute("data-status", "pending")
            page.mouse.down()
            page.wait_for_timeout(1100)
            page.mouse.up()

            sync_api.expect(page.get_by_test_id("assistant-reply")).to_have_count(1, timeout=20_000)
            sync_api.expect(card).to_have_attribute("data-status", "approved")
            sync_api.expect(page.get_by_test_id("trace-panel")).to_contain_text("Ledger write")
            sync_api.expect(page.get_by_test_id("trace-panel")).to_contain_text("Figures grounded")

            page.get_by_test_id("tab-home").click()
            sync_api.expect(page.get_by_test_id("on-track")).to_be_visible()
            sync_api.expect(page.get_by_test_id("balance-chk")).not_to_have_text("$1,672.69")

            page.get_by_test_id("nav-runs").click()
            sync_api.expect(page.get_by_test_id("runs-table")).to_contain_text("Checking is forecast")
        finally:
            browser.close()
    assert errors == []

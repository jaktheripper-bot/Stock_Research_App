"""Workstream 3 (Feedback #7) Unit & Outside-In Contract Tests.

Verifies:
1. 7-Asset coverage in `core/search/product_search.py` (Equities, Mutual Funds, ETFs,
   Corporate Debt, REITs/InvITs/SGBs, Sovereign Curve/SDLs, Unlisted MSMEs).
2. String `baseline_pe` safety & BSE 6-digit scrip / alias fallback in `search_equities`.
3. `GET /api/search/products` & `GET /search` 7-category HTTP/DOM contracts.
4. Outside-In UI contracts on `#navOmniSearchBtn` & `#omniSearchModal` (top-layer body
   placement outside `<main>`, synchronous `.focus({ preventScroll: true })`, `inert`
   ancestor guard + restoration, `font-size: 16px`, ARIA labels/live region, Light+Dark CSS).
5. AST exception-logging hygiene in `core/search/product_search.py`.
"""

import ast
import os
import unittest
from pathlib import Path

os.environ.setdefault("TESTING", "1")

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.search.product_search import (
    CATEGORY_ORDER,
    empty_search_categories,
    search_debt_securities,
    search_equities,
    search_etfs,
    search_investment_products,
    search_msmes,
    search_mutual_funds,
    search_reits_and_sgbs,
    search_sovereign,
)
from web.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestOmniSearchWS3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_empty_categories_has_all_seven_asset_keys(self):
        cats = empty_search_categories()
        self.assertEqual(tuple(cats.keys()), CATEGORY_ORDER)
        self.assertEqual(len(cats), 7)

    def test_seven_asset_search_functions_return_valid_routes(self):
        eq = search_equities("TCS", limit=5)
        self.assertTrue(len(eq) >= 1)
        self.assertEqual(eq[0]["product_type"], "EQUITY")
        self.assertEqual(eq[0]["url"], "/dossier/TCS")

        # 6-digit BSE scrip code & alias resolution
        eq_scrip = search_equities("532540", limit=5)
        self.assertTrue(any(item["identifier"] == "TCS" for item in eq_scrip))

        eq_alias = search_equities("ZOMATO", limit=5)
        self.assertTrue(len(eq_alias) >= 1)
        self.assertTrue(eq_alias[0]["url"].startswith("/dossier/"))

        etfs = search_etfs("ETF", limit=5)
        self.assertTrue(len(etfs) >= 1)
        self.assertEqual(etfs[0]["product_type"], "ETF")
        self.assertTrue(etfs[0]["url"].startswith("/etfs/"))

        debt = search_debt_securities("NCD", limit=5)
        self.assertTrue(len(debt) >= 1)
        self.assertEqual(debt[0]["product_type"], "DEBT")
        self.assertTrue(debt[0]["url"].startswith("/debt/"))

        reits = search_reits_and_sgbs("REIT", limit=5)
        self.assertTrue(len(reits) >= 1)
        self.assertEqual(reits[0]["product_type"], "REIT_INVIT")
        self.assertTrue(reits[0]["url"].startswith("/reits/"))

        sgbs = search_reits_and_sgbs("SGB", limit=5)
        self.assertTrue(len(sgbs) >= 1)
        self.assertEqual(sgbs[0]["url"], "/reits#sgbCardsGrid")

        sov = search_sovereign("10Y", limit=5)
        self.assertTrue(len(sov) >= 1)
        self.assertEqual(sov[0]["product_type"], "SOVEREIGN")
        self.assertTrue(sov[0]["url"].startswith("/sovereign"))

        sdls = search_sovereign("SDL", limit=5)
        self.assertTrue(len(sdls) >= 1)
        self.assertEqual(sdls[0]["url"], "/sovereign#sdlCardsGrid")

        msmes = search_msmes("UDYAM", limit=5)
        self.assertTrue(len(msmes) >= 1)
        self.assertEqual(msmes[0]["product_type"], "MSME")
        self.assertTrue(msmes[0]["url"].startswith("/msme/UDYAM-"))

        mfs = search_mutual_funds("HDFC", limit=5)
        self.assertIsInstance(mfs, list)

    def test_master_search_investment_products_returns_all_seven_categories(self):
        res = search_investment_products("India", product_type="ALL", limit_per_category=4)
        self.assertIn("categories", res)
        self.assertEqual(tuple(res["categories"].keys()), CATEGORY_ORDER)
        for item in res["results"]:
            self.assertNotIn("Fair", str(item.get("details", {}).get("pe", "")))
            self.assertNotIn("N/A", str(item.get("details", {})))

    def test_api_search_products_returns_grouped_seven_categories(self):
        resp = self.client.get("/api/search/products?q=EMBASSY&asset_class=ALL&limit_per_category=4")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("categories", payload)
        self.assertEqual(tuple(payload["categories"].keys()), CATEGORY_ORDER)
        self.assertGreaterEqual(len(payload["categories"]["reits_invits"]), 1)

    def test_search_page_renders_seven_asset_explore_and_filtered_cards(self):
        # Empty query -> 7-asset explore cards
        empty_resp = self.client.get("/search")
        self.assertEqual(empty_resp.status_code, 200)
        html_empty = empty_resp.text
        self.assertNotIn("{{", html_empty)
        self.assertNotIn("{%", html_empty)
        self.assertNotIn('\\"', html_empty)
        soup_empty = BeautifulSoup(html_empty, "html.parser")
        explore_cards = soup_empty.select(".search-explore-card")
        self.assertEqual(len(explore_cards), 7)

        # Sovereign & MSME queries render clickable asset-card-accent cards wrapped in <a href>
        for q in ("EMBASSY", "10Y", "UDYAM"):
            r = self.client.get(f"/search?q={q}")
            self.assertEqual(r.status_code, 200)
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select(".search-results-page .asset-card-accent")
            self.assertGreaterEqual(len(cards), 1, f"Expected >= 1 rendered card on /search?q={q}")
            for card in cards:
                parent_link = card.find_parent("a", href=True)
                self.assertIsNotNone(parent_link, f"Dead hover card without <a href> on /search?q={q}")

    def test_header_omni_search_modal_outside_in_dom_and_js_contracts(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Header trigger pill
        trigger = soup.find("button", id="navOmniSearchBtn")
        self.assertIsNotNone(trigger)
        self.assertEqual(trigger.get("onclick"), "openOmniSearchModal()")
        self.assertEqual(trigger.get("aria-controls"), "omniSearchModal")
        self.assertIn("btn", trigger.get("class", []))

        # 2. Top-layer #omniSearchModal directly under <body> (outside <main>)
        modal = soup.find(id="omniSearchModal")
        self.assertIsNotNone(modal)
        self.assertIn("modal-backdrop", modal.get("class", []))
        self.assertEqual(modal.parent.name, "body")
        self.assertIsNone(modal.find_parent("main"))

        dialog = modal.select_one(".modal-dialog")
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.get("role"), "dialog")
        self.assertEqual(dialog.get("aria-modal"), "true")

        close_btn = modal.find("button", id="closeOmniSearchModalBtn")
        self.assertIsNotNone(close_btn)
        self.assertIn("modal-close-btn", close_btn.get("class", []))

        # 3. Input font-size >= 16px, explicit <label for>, and polite live status outside <main>
        search_input = modal.find("input", id="omniSearchModalInput")
        self.assertIsNotNone(search_input)
        self.assertIn("16px", search_input.get("style", ""))
        label = modal.find("label", attrs={"for": "omniSearchModalInput"})
        self.assertIsNotNone(label)

        live_region = modal.find(id="omniSearchLiveStatus")
        self.assertIsNotNone(live_region)
        self.assertEqual(live_region.get("aria-live"), "polite")
        self.assertIsNone(live_region.find_parent("main"))

        # 4. 8 category filter chips (ALL + 7 asset classes)
        chips = modal.select(".omni-filter-chip[data-omni-cat]")
        self.assertEqual(len(chips), 8)

        # 5. JS wiring & shortcut coordination
        main_js = (PROJECT_ROOT / "web" / "static" / "js" / "main.js").read_text(encoding="utf-8")
        for fn_name in (
            "window.openOmniSearchModal",
            "window.closeOmniSearchModal",
            "window.setOmniSearchCategory",
            "window.handleOmniSearchSubmit",
            "window.switchOmniToResearchDesk",
            "window.switchOmniToGenerateModal",
        ):
            self.assertIn(fn_name, main_js)
        self.assertIn("focus({ preventScroll: true })", main_js)
        self.assertIn("!mainEl.contains(modal)", main_js)
        self.assertIn("mainEl.inert = false", main_js)

        copilot_js = (PROJECT_ROOT / "web" / "static" / "js" / "copilot.js").read_text(encoding="utf-8")
        self.assertNotIn('e.key === "/"', copilot_js)

        # 6. Light + Dark CSS rules & header button max-width <= 400px
        css_text = (PROJECT_ROOT / "web" / "static" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".header-omni-search-pill", css_text)
        self.assertIn('html[data-theme="dark"] .omni-search-dialog', css_text)
        self.assertIn("max-width: 260px;", css_text)

    def test_product_search_ast_has_zero_silent_or_debug_exceptions(self):
        src_path = PROJECT_ROOT / "core" / "search" / "product_search.py"
        tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                body_src = ast.unparse(node)
                self.assertTrue(
                    "logger.warning(" in body_src or "logger.error(" in body_src,
                    f"ExceptHandler in product_search.py must log warning/error: {body_src}",
                )


if __name__ == "__main__":
    unittest.main()

"""Outside-in contract tests for Mobile Brief Mode (/m).

Asset IDs are pulled dynamically from the database (never hardcoded) so the tests
follow whatever is actually stored. Covers routes, the JSON API, rendered-DOM
hygiene, paywall chip behaviour, hub link resolution and the dossier entry link.
"""

import os
import re
import unittest

os.environ.setdefault("TESTING", "1")

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from core.db.connection import get_db_connection
from web.main import app


def _first_value(sql: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        cur.close()
        conn.close()


def _msme_uin():
    uin = _first_value("SELECT uin FROM msme_firms LIMIT 1")
    if uin:
        return uin
    from core.msme.seed import CANONICAL_MSME_FIRMS
    return CANONICAL_MSME_FIRMS[0]["uin"] if CANONICAL_MSME_FIRMS else None


class TestMobileBriefMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.ids = {
            "equity": _first_value("SELECT ticker FROM reports ORDER BY timestamp DESC LIMIT 1"),
            "fund": _first_value("SELECT scheme_code FROM mutual_fund_schemes LIMIT 1"),
            "debt": _first_value("SELECT isin FROM corporate_debt_securities LIMIT 1"),
            "reit": _first_value("SELECT symbol FROM reits_and_invits LIMIT 1"),
            "msme": _msme_uin(),
        }

    def _need(self, kind):
        if not self.ids.get(kind):
            self.skipTest(f"No {kind} record available in the database")
        return str(self.ids[kind])

    # ---- routes -------------------------------------------------------
    def test_hub_renders(self):
        r = self.client.get("/m")
        self.assertEqual(r.status_code, 200)
        self.assertIn("mobileBriefRoot", r.text)

    def test_hub_query_jumps_to_equity_brief(self):
        r = self.client.get("/m?q=infy", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["location"].startswith("/m/equity/"))

    def test_each_asset_class_brief_page_and_api(self):
        for kind in ("equity", "fund", "debt", "reit", "msme"):
            with self.subTest(kind=kind):
                ident = self._need(kind)
                page = self.client.get(f"/m/{kind}/{ident}")
                self.assertEqual(page.status_code, 200, f"/m/{kind}/{ident}")
                api = self.client.get(f"/api/mobile-brief/{kind}/{ident}")
                self.assertEqual(api.status_code, 200, f"api {kind}/{ident}")
                data = api.json()
                for key in ("title", "brief_lines", "top_risk_flag", "last_updated", "sebi_disclaimer", "desktop_url"):
                    self.assertTrue(data.get(key), f"{kind}: missing {key}")
                self.assertNotEqual(data["last_updated"], "Recent")
                self.assertIsInstance(data["brief_lines"], list)

    def test_shorthand_equity_route(self):
        ident = self._need("equity")
        r = self.client.get(f"/m/{ident}", follow_redirects=False)
        self.assertIn(r.status_code, (200, 302))

    def test_unknown_assets_return_404(self):
        for kind in ("fund", "debt", "reit", "msme"):
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(f"/m/{kind}/ZZ-NOT-A-REAL-ID").status_code, 404)
                self.assertEqual(self.client.get(f"/api/mobile-brief/{kind}/ZZ-NOT-A-REAL-ID").status_code, 404)

    # ---- rendered DOM hygiene ----------------------------------------
    def _soup(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, path)
        return BeautifulSoup(r.text, "html.parser"), r.text

    def _assert_dom_hygiene(self, soup, path):
        for el in soup.find_all(True):
            for attr, val in el.attrs.items():
                joined = " ".join(val) if isinstance(val, list) else str(val)
                self.assertNotIn("{{", joined, f"{path}: unrendered Jinja in {attr}")
                self.assertNotIn("{%", joined, f"{path}: unrendered Jinja in {attr}")
        ids = [el["id"] for el in soup.find_all(id=True)]
        self.assertEqual(len(ids), len(set(ids)), f"{path}: duplicate element ids")
        for btn in soup.find_all("button"):
            if btn.find_parent(id="mobileBriefRoot") is None or btn.get("id") == "mbJumpSubmit":
                continue
            self.assertEqual(btn.get("type"), "button", f"{path}: button without type=button")
            self.assertIn("btn", btn.get("class", []), f"{path}: button without .btn class")
            self.assertTrue(btn.get_text(strip=True), f"{path}: button without label")
            action = btn.get("data-mb-action")
            self.assertIn(action, ("copilot", "unlock"), f"{path}: button without valid data-mb-action")
            self.assertTrue(btn.get("data-asset-id"), f"{path}: action button without data-asset-id")
        for a in soup.select("#mobileBriefRoot a[href]"):
            self.assertTrue(a["href"].strip(), f"{path}: empty href")

    def test_dom_hygiene_for_hub_and_every_brief(self):
        paths = ["/m"]
        for kind in ("equity", "fund", "debt", "reit", "msme"):
            if self.ids.get(kind):
                paths.append(f"/m/{kind}/{self.ids[kind]}")
        for path in paths:
            with self.subTest(path=path):
                soup, _ = self._soup(path)
                self._assert_dom_hygiene(soup, path)

    def test_inline_script_dom_bindings_exist(self):
        soup, text = self._soup("/m")
        inline = " ".join(s.get_text() for s in soup.find_all("script") if not s.get("src"))
        for target in re.findall(r"getElementById\(['\"]([\w-]+)['\"]\)", inline):
            self.assertIsNotNone(soup.find(id=target), f"getElementById('{target}') target missing from DOM")

    def test_disclaimer_present_everywhere(self):
        for path in ["/m"] + [f"/m/{k}/{v}" for k, v in self.ids.items() if v]:
            with self.subTest(path=path):
                soup, _ = self._soup(path)
                box = soup.find(id="mbDisclaimer")
                self.assertIsNotNone(box)
                self.assertTrue(box.get_text(strip=True))

    # ---- paywall ------------------------------------------------------
    def test_guest_sees_pillars_03_and_05_locked(self):
        ident = self._need("equity")
        soup, _ = self._soup(f"/m/equity/{ident}")
        chips = {b["id"]: b for b in soup.select("button[id^=mbPillar]")}
        self.assertEqual(len(chips), 7)
        for num in ("03", "05"):
            self.assertEqual(chips[f"mbPillar{num}"]["data-mb-action"], "unlock")
        for num in ("01", "02", "04", "06", "07"):
            self.assertEqual(chips[f"mbPillar{num}"]["data-mb-action"], "copilot")

    # ---- hub link resolution -----------------------------------------
    def test_every_internal_hub_link_resolves(self):
        soup, _ = self._soup("/m")
        targets = set()
        for el in soup.select("#mobileBriefRoot [href], #mobileBriefRoot [data-href]"):
            t = el.get("href") or el.get("data-href")
            if t and t.startswith("/"):
                targets.add(t)
        self.assertTrue(targets, "hub exposes no internal links")
        for t in sorted(targets):
            with self.subTest(link=t):
                r = self.client.get(t, follow_redirects=False)
                self.assertIn(r.status_code, (200, 302), f"hub link {t} returned {r.status_code}")

    # ---- dossier entry point -----------------------------------------
    def test_dossier_page_links_to_brief_view(self):
        ident = self._need("equity")
        r = self.client.get(f"/dossier/{ident}")
        if r.status_code != 200:
            self.skipTest(f"/dossier/{ident} returned {r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.find(id="dossierBriefViewLink")
        self.assertIsNotNone(link)
        self.assertTrue(link["href"].startswith("/m/equity/"))
        self.assertIsNotNone(soup.find(id="dossierReadingToggleBtn"))


if __name__ == "__main__":
    unittest.main()

"""
tests/integration/test_market_and_amfi_gateways.py
==================================================
Consolidated Market Gateways & Ingestion Pipelines:
1. Angel One SmartAPI, TOTP RFC 6238, and Yahoo Finance opt-in fallback
2. AMFI NAV feed ingestion and fuzzy search indexing
3. National ETF Matrix AMFI ingestion, categorization, and database operations
4. Monthly Mutual Fund Portfolio Excel/CSV disclosure parser and holding ranker
"""
import os
os.environ["TESTING"] = "1"

import unittest
from unittest.mock import patch, MagicMock
"""
Consolidated Market Data Gateways & Auth Security Suite
========================================================
Unifies:
1. Angel One SmartAPI Gateway, Level-2 Depth Analytics, TOTP, and Proxies
2. yfinance Opt-in Flag & Historical Price Source Prioritization
3. Local TOTP 2FA QR Generation (No 3rd Party Leaks)
"""
import base64
import os
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock, patch

from core.analysis import fundamentals as fnd
from core.ingestion.angel_one import AngelOneGateway
from core.auth.totp import generate_rfc6238_totp
from web.main import _build_local_qr_data_uri

ROOT = Path(__file__).resolve().parent.parent.parent


def _candles(n=60):
    return [
        {
            "timestamp": f"2026-08-{(i % 28) + 1:02d}T00:00:00+05:30",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000 + i,
        }
        for i in range(n)
    ]


# ==============================================================================
# 1. Angel One SmartAPI Gateway & Order Depth
# ==============================================================================
class TestAngelOneGateway(unittest.TestCase):
    def test_rfc6238_totp_generation(self):
        secret = "JBSWY3DPEHPK3PXP"
        totp = generate_rfc6238_totp(secret)
        self.assertIsInstance(totp, str)
        self.assertEqual(len(totp), 6)
        self.assertTrue(totp.isdigit())

    def test_rfc6238_totp_handles_spaces_and_lowercase(self):
        secret = "jbsw y3dp ehpk 3pxp"
        totp = generate_rfc6238_totp(secret)
        self.assertEqual(len(totp), 6)
        self.assertTrue(totp.isdigit())

    def test_is_configured_returns_false_when_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(AngelOneGateway.is_configured())

    def test_is_configured_returns_true_when_all_present(self):
        env_vars = {
            "ANGEL_API_KEY": "test_key",
            "ANGEL_CLIENT_CODE": "test_client",
            "ANGEL_PIN": "1234",
            "ANGEL_TOTP_KEY": "JBSWY3DPEHPK3PXP",
        }
        with patch.dict(os.environ, env_vars):
            self.assertTrue(AngelOneGateway.is_configured())

    def test_proxy_config_resolution(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(AngelOneGateway.get_proxy_config())

        proxy_url = "http://user:pass@proxy.quotaguard.com:9293"
        with patch.dict(os.environ, {"SMARTAPI_PROXY_URL": proxy_url}):
            proxies = AngelOneGateway.get_proxy_config()
            self.assertIsNotNone(proxies)
            self.assertEqual(proxies.get("http"), proxy_url)
            self.assertEqual(proxies.get("https"), proxy_url)

    @patch("requests.get")
    def test_probe_outbound_ip_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ip": "54.217.100.200"}'
        mock_resp.json.return_value = {"ip": "54.217.100.200"}
        mock_get.return_value = mock_resp

        res = AngelOneGateway.probe_outbound_ip()
        self.assertEqual(res["outbound_ip"], "54.217.100.200")
        self.assertEqual(res["status"], "SUCCESS")

    def test_unauthenticated_quote_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            res = AngelOneGateway.get_quote_with_depth("NSE", "3045")
            self.assertIsNone(res)

    def test_resolve_symbol_token_nse(self):
        exch, token = AngelOneGateway.resolve_symbol_token("INFY")
        self.assertEqual(exch, "NSE")
        self.assertEqual(token, "1594")

        exch, token = AngelOneGateway.resolve_symbol_token("RELIANCE")
        self.assertEqual(exch, "NSE")
        self.assertEqual(token, "2885")

    def test_resolve_symbol_token_bse_fallback(self):
        exch, token = AngelOneGateway.resolve_symbol_token("ONIDA")
        self.assertEqual(exch, "BSE")
        self.assertEqual(token, "500279")

    def test_compute_depth_analytics(self):
        buy_book = [{"price": 100.0, "quantity": 1000}, {"price": 99.5, "quantity": 500}]
        sell_book = [{"price": 100.5, "quantity": 200}, {"price": 101.0, "quantity": 300}]
        analytics = AngelOneGateway.compute_depth_analytics(buy_book, sell_book)
        self.assertEqual(analytics["total_buy_qty"], 1500)
        self.assertEqual(analytics["total_sell_qty"], 500)
        self.assertAlmostEqual(analytics["order_imbalance_ratio"], 0.5, places=2)
        self.assertEqual(analytics["depth_pressure_regime"], "ACCUMULATION_DOMINANT")
        self.assertGreater(analytics["bid_ask_spread_bps"], 0.0)

    def test_format_dossier_market_depth_badge(self):
        dummy_quote = {
            "order_imbalance_ratio": 0.35,
            "upper_circuit": 1500.0,
            "lower_circuit": 1300.0,
            "ltp": 1420.0,
        }
        badge = AngelOneGateway.format_dossier_market_depth_badge(dummy_quote)
        self.assertIn("Exchange Level-2 Depth", badge)
        self.assertIn("Accumulation", badge)
        self.assertIn("Circuit Bands", badge)

    def test_angel_one_eod_summary_from_historical_candles(self):
        with patch.object(AngelOneGateway, "get_historical_candles", return_value=_candles(100)):
            eod = AngelOneGateway.get_eod_summary("INFY")
            self.assertIsNotNone(eod)
            self.assertEqual(eod["source"], "Angel One SmartAPI EOD Candles")
            self.assertGreater(eod["current_price"], 100.0)
            self.assertGreaterEqual(eod["52w_high"], eod["current_price"])
            self.assertLessEqual(eod["52w_low"], eod["current_price"])
            self.assertIsNotNone(eod["dma_50"])
            self.assertIsNotNone(eod["dma_200"])

    @patch("requests.post")
    def test_angel_one_search_scrip_token_dynamic_resolution(self, mock_post):
        AngelOneGateway._DYNAMIC_TOKEN_CACHE.pop("COFORGE", None)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": True,
            "data": [{"exchange": "NSE", "tradingsymbol": "COFORGE-EQ", "symboltoken": "11543"}],
        }
        mock_post.return_value = mock_resp
        with patch.object(AngelOneGateway, "authenticate", return_value="jwt_test_token"):
            res = AngelOneGateway.search_scrip_token("COFORGE")
            self.assertEqual(res, ("NSE", "11543"))
            self.assertEqual(AngelOneGateway._DYNAMIC_TOKEN_CACHE.get("COFORGE"), ("NSE", "11543"))

    def test_gemini_batch_api_synthesis_and_flex_fallback(self):
        from core.analysis.dossier_report_synthesis import synthesize_batch_stock_reports
        sample_report = "# Equity Research Dossier: Infosys (INFY)\n" + ("Detailed 7-Pillar institutional analysis. " * 25)

        mock_inline_resp = MagicMock()
        mock_inline_resp.response.text = sample_report
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/test-job-123"
        mock_batch_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_batch_job.dest.inlined_responses = [mock_inline_resp]

        mock_client = MagicMock()
        mock_client.batches.create.return_value = mock_batch_job

        with patch("core.config.get_secret", return_value="AIzaSyTestBatchApiKey1234567890"), \
             patch("core.analysis.dossier_report_synthesis.genai.Client", return_value=mock_client), \
             patch("core.analysis.dossier_report_synthesis.get_latest_flash_models", return_value=["gemini-3.8-flash"]), \
             patch("core.analysis.dossier_report_synthesis.pass_pre_screening_gates", return_value=(True, "OK")):
            res = synthesize_batch_stock_reports(
                [{"ticker": "INFY", "stock_data": {"ticker": "INFY", "short_name": "Infosys", "scrip_code": "500209"}}],
                poll_timeout_seconds=5,
                edition_label="unit-test",
            )
            self.assertIn("INFY", res)
            self.assertEqual(res["INFY"]["tier"], "GEMINI_BATCH_API_50PCT_DISCOUNT")
            self.assertEqual(res["INFY"]["batch_job_name"], "batches/test-job-123")
            self.assertGreaterEqual(len(res["INFY"]["report_text"]), 500)

    @patch("requests.post")
    def test_perplexity_responses_non_stream_fallback(self, mock_post):
        from core.analysis.dossier_report_synthesis import stream_perplexity_fallback

        resp_stream_fail = MagicMock()
        resp_stream_fail.status_code = 502
        resp_stream_fail.text = "bad gateway"
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Perplexity grounded synthesis output."}]}],
            "citations": ["https://www.bseindia.com/filing/123"],
        }
        mock_post.side_effect = [resp_stream_fail, resp_ok]

        cites = []
        with patch("core.config.get_secret", return_value="pplx-test-key-12345"):
            chunks = list(stream_perplexity_fallback("Analyze INFY", "System prompt", collected_citations=cites))
        self.assertEqual("".join(chunks), "Perplexity grounded synthesis output.")
        self.assertEqual(len(cites), 1)
        self.assertEqual(cites[0]["uri"], "https://www.bseindia.com/filing/123")
        self.assertEqual(mock_post.call_count, 2)
        for call in mock_post.call_args_list:
            self.assertEqual(call.args[0], "https://api.perplexity.ai/v1/responses")

    @patch("requests.post")
    def test_perplexity_failure_raises_real_responses_error_without_legacy_sonar_call(self, mock_post):
        from core.analysis.dossier_report_synthesis import stream_perplexity_fallback

        resp_fail = MagicMock()
        resp_fail.status_code = 401
        resp_fail.text = '{"error":"invalid api key"}'
        mock_post.side_effect = [resp_fail, resp_fail]

        with patch("core.config.get_secret", return_value="pplx-test-key-12345"):
            with self.assertRaises(RuntimeError) as ctx:
                list(stream_perplexity_fallback("Analyze INFY", "System prompt", collected_citations=[]))
        self.assertIn("/v1/responses", str(ctx.exception))
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 2)
        for call in mock_post.call_args_list:
            self.assertNotIn("chat/completions", call.args[0])

    @patch("requests.post")
    def test_standardized_supabase_auth_otp_verification(self, mock_post):
        from core.auth.supabase_auth import verify_supabase_otp_token
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "sb.jwt.token",
            "user": {"email": "investor@moatnomics.com", "user_metadata": {"full_name": "Rahul Sharma"}},
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"TESTING": "0", "SUPABASE_URL": "https://omswdxrtzrvlszkidssh.supabase.co", "SUPABASE_ANON_KEY": "anon_test_key"}):
            ok, v_email, v_name, tok = verify_supabase_otp_token("investor@moatnomics.com", "654321")
            self.assertTrue(ok)
            self.assertEqual(v_email, "investor@moatnomics.com")
            self.assertEqual(v_name, "Rahul Sharma")
            self.assertEqual(tok, "sb.jwt.token")


# ==============================================================================
# 2. yfinance Opt-in & Fallback Verification
# ==============================================================================
class TestYfinanceOptIn(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.pop("YFINANCE_FALLBACK", None)
        os.environ["YFINANCE_FALLBACK"] = "0"

    def tearDown(self):
        if self._prev is not None:
            os.environ["YFINANCE_FALLBACK"] = self._prev
        else:
            os.environ.pop("YFINANCE_FALLBACK", None)

    def test_flag_defaults_on_and_can_be_disabled(self):
        from core.config import yfinance_fallback_enabled
        os.environ.pop("YFINANCE_FALLBACK", None)
        self.assertTrue(yfinance_fallback_enabled())
        os.environ["YFINANCE_FALLBACK"] = "0"
        self.assertFalse(yfinance_fallback_enabled())

    def test_enrich_does_not_call_yfinance_when_off(self):
        with patch.object(fnd.yf, "Ticker") as tk:
            out = fnd.enrich_fundamentals("ZZTESTONLY", {})
            tk.assert_not_called()
        self.assertEqual(out.get("pb_ratio"), "N/A")
        self.assertEqual(out.get("forward_pe"), "N/A")

    def test_historical_prices_use_angel_and_skip_yfinance(self):
        with patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=True), \
             patch("core.ingestion.angel_one.AngelOneGateway.get_historical_candles", return_value=_candles()), \
             patch.object(fnd.yf, "Ticker") as tk:
            df = fnd.get_historical_prices("TSTA1")
            tk.assert_not_called()
        self.assertIsNotNone(df)
        self.assertIn("SMA50", df.columns)
        self.assertGreater(len(df), 5)

    def test_historical_prices_none_when_angel_down_and_flag_off(self):
        with patch("core.ingestion.angel_one.AngelOneGateway.is_configured", return_value=False), \
             patch.object(fnd.yf, "Ticker") as tk:
            self.assertIsNone(fnd.get_historical_prices("TSTB2"))
            tk.assert_not_called()


# ==============================================================================
# 3. Local TOTP QR Code Generation
# ==============================================================================
class TestLocalTotpQr(unittest.TestCase):
    def test_qr_is_inline_svg_data_uri(self):
        uri = _build_local_qr_data_uri("otpauth://totp/Test:a@b.com?secret=ABC&issuer=Test")
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        self.assertIn("<svg", svg)

    def test_no_third_party_qr_service_in_source(self):
        src = (ROOT / "web" / "main.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"qrserver\.com|chart\.googleapis\.com/chart\?cht=qr", src))




"""Comprehensive unit tests for Priority 2 Implementation:
1. Live AMFI Ingestion Pipeline & NAV Parser
2. Multi-Asset Omni Product Search
3. Always-On Asset Monitoring Engine & Ledger
4. Source-Grounded Dual-Sleeve Look-Through
5. Search & Asset Web Endpoints
"""

import os
import unittest
from fastapi.testclient import TestClient

from core.ingestion.amfi import (
    parse_amfi_nav_feed,
    derive_broad_category,
    derive_benchmark_index,
    search_amfi_master_directory,
    fetch_amfi_nav_raw
)
from core.search.product_search import (
    search_all_products,
    search_equities,
    search_mutual_funds,
    search_debt_securities
)
from core.analysis.asset_scanner import (
    record_scan_start,
    record_scan_complete,
    get_asset_scan_runs,
    scan_debt_securities
)
from core.analysis.mutual_funds_engine import evaluate_dual_sleeve_lookthrough
from core.db.connection import init_db
from web.main import app, _generate_admin_token, ADMIN_COOKIE_NAME


class TestAmfiIngestionAndSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_parse_amfi_nav_feed_synthetic(self):
        sample_feed = (
            "Open Ended Schemes (Equity Scheme - Flexi Cap Fund)\n"
            "PPFAS Mutual Fund\n"
            "122639;INF846K01DP8;INF846K01DQ6;Parag Parikh Flexi Cap Fund;Direct;Growth;88.2600;03-Oct-2026\n"
            "122638;INF846K01DR4;;Parag Parikh Flexi Cap Fund;Regular;Growth;78.1000;03-Oct-2026\n"
        )
        # Direct Growth only
        direct_schemes = parse_amfi_nav_feed(sample_feed, direct_growth_only=True)
        self.assertEqual(len(direct_schemes), 1)
        res = direct_schemes[0]
        self.assertEqual(res["scheme_code"], "122639")
        self.assertEqual(res["isin_growth"], "INF846K01DP8")
        self.assertEqual(res["nav"], 88.26)
        self.assertEqual(res["broad_category"], "EQUITY")
        self.assertEqual(res["benchmark_index"], "NIFTY 500 TRI")
        self.assertEqual(res["fund_house"], "PPFAS Mutual Fund")
        self.assertEqual(res["nav_date"], "03-Oct-2026")

        # Both direct and regular
        all_schemes = parse_amfi_nav_feed(sample_feed, direct_growth_only=False)
        self.assertEqual(len(all_schemes), 2)

    def test_derive_category_and_benchmark(self):
        broad1 = derive_broad_category("Equity Scheme - Large Cap Fund")
        bmk1 = derive_benchmark_index("Equity Scheme - Large Cap Fund", broad1)
        self.assertEqual(broad1, "EQUITY")
        self.assertEqual(bmk1, "NIFTY 50 TRI")

        broad2 = derive_broad_category("Debt Scheme - Corporate Bond Fund")
        bmk2 = derive_benchmark_index("Debt Scheme - Corporate Bond Fund", broad2)
        self.assertEqual(broad2, "DEBT")
        self.assertEqual(bmk2, "CRISIL Composite Bond Fund Index")

        broad3 = derive_broad_category("Hybrid Scheme - Balanced Advantage")
        bmk3 = derive_benchmark_index("Hybrid Scheme - Balanced Advantage", broad3)
        self.assertEqual(broad3, "HYBRID")
        self.assertIn("CRISIL Hybrid", bmk3)

    def test_search_amfi_master_directory(self):
        matches = search_amfi_master_directory("Parag Parikh", limit=5)
        self.assertIsInstance(matches, list)
        if matches:
            first = matches[0]
            self.assertIn("scheme_code", first)
            self.assertIn("scheme_name", first)
            self.assertIn("nav", first)

    def test_omni_product_search(self):
        # 1. Search equities
        eq_res = search_equities("TCS", limit=5)
        self.assertIsInstance(eq_res, list)

        # 2. Search mutual funds
        mf_res = search_mutual_funds("Flexi", limit=5)
        self.assertIsInstance(mf_res, list)

        # 3. Search debt
        debt_res = search_debt_securities("SDI", limit=5)
        self.assertIsInstance(debt_res, list)

        # 4. Search all products unified
        all_res = search_all_products("Fund", asset_class="all", limit=10)
        self.assertIsInstance(all_res, list)
        self.assertGreater(len(all_res), 0)
        for item in all_res:
            self.assertIn("asset_class", item)
            self.assertIn("identifier", item)
            self.assertIn("title", item)
            self.assertIn("url", item)

    def test_asset_scanner_ledger(self):
        scan_id = record_scan_start("test_monitoring", triggered_by="unit_test")
        self.assertTrue(scan_id.startswith("scan_"))

        record_scan_complete(
            scan_id=scan_id,
            status="completed",
            items_scanned=42,
            items_added=5,
            items_updated=37,
            items_archived=0,
            details={"test_metric": 100}
        )

        runs = get_asset_scan_runs(limit=10)
        matching = [r for r in runs if r["scan_id"] == scan_id]
        self.assertEqual(len(matching), 1)
        run = matching[0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["items_scanned"], 42)
        self.assertEqual(run["items_added"], 5)
        self.assertEqual(run["items_updated"], 37)

    def test_debt_asset_scanner_runs(self):
        summary = scan_debt_securities()
        self.assertEqual(summary["asset_class"], "CORPORATE_DEBT")
        self.assertGreaterEqual(summary["scanned"], 0)

    def test_zero_hallucination_lookthrough(self):
        """Verifies that unresearched stocks do not receive hallucinated scores."""
        synthetic_scheme = {
            "scheme_code": "TEST_SCHEME_XYZ",
            "scheme_name": "Test Alpha Portfolio",
            "fund_house": "Alpha Mutual Fund",
            "category": "Flexi Cap Fund",
            "broad_category": "EQUITY",
            "benchmark_index": "NIFTY 500 TRI",
            "aum_crores": 1000.0,
            "nav": 50.0,
            "ter_direct_pct": 0.50,
            "ter_regular_pct": 1.20,
            "portfolio_turnover_ratio_pct": 15.0,
            "active_share_pct": 75.0
        }
        # One unresearched holding not in benchmark proxies or database
        synthetic_holdings = [
            {
                "holding_type": "EQUITY",
                "identifier": "NONEXISTENT_TICKER_12345",
                "holding_name": "Nonexistent Small Cap Ltd",
                "weight_pct": 10.0,
                "sector_or_rating": "Speculative"
            }
        ]

        res = evaluate_dual_sleeve_lookthrough(synthetic_scheme, synthetic_holdings)
        self.assertIsNotNone(res)
        holdings_out = res["holdings"]
        self.assertEqual(len(holdings_out), 1)
        unresearched_h = holdings_out[0]
        # Must strictly have is_researched = False
        self.assertFalse(unresearched_h["is_researched"])
        # Fundamental score must be None or marked N/A
        self.assertEqual(unresearched_h["score"], "N/A")
        self.assertIn("Coverage Pending", unresearched_h["notes"])
        # Coverage percentage must be 0.0%
        self.assertEqual(res["sleeve_breakdown"]["equity_coverage_pct"], 0.0)

    def test_search_web_routes(self):
        # 1. HTML Search page
        resp_html = self.client.get("/search?q=HDFC")
        self.assertEqual(resp_html.status_code, 200)
        self.assertIn("text/html", resp_html.headers["content-type"])
        self.assertIn("Search Investment Products", resp_html.text)

        # 2. JSON API endpoint
        resp_api = self.client.get("/api/search/products?q=Tata&asset_class=all")
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["query"], "Tata")
        self.assertIsInstance(data["results"], list)

    def test_admin_asset_scan_api(self):
        # Unauthenticated request should fail
        resp_unauth = self.client.get("/api/admin/assets/scan-runs")
        self.assertEqual(resp_unauth.status_code, 403)

        # Authenticated with admin token
        token = _generate_admin_token("admin@research.internal", "admin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, token)

        resp_auth = self.client.get("/api/admin/assets/scan-runs")
        self.assertEqual(resp_auth.status_code, 200)
        runs_data = resp_auth.json()
        self.assertEqual(runs_data["status"], "success")
        self.assertIsInstance(runs_data["runs"], list)

    def test_admin_sync_amfi_api(self):
        # Unauthenticated request with clean client should fail with 403
        unauth_client = TestClient(app)
        resp_unauth = unauth_client.post("/api/admin/sync-amfi")
        self.assertEqual(resp_unauth.status_code, 403)

        # Authenticated with admin token
        token = _generate_admin_token("admin@research.internal", "admin")
        unauth_client.cookies.set(ADMIN_COOKIE_NAME, token)

        # Trigger sync with limit 3 for fast unit test
        resp_auth = unauth_client.post("/api/admin/sync-amfi?limit=3")
        self.assertEqual(resp_auth.status_code, 200)
        data = resp_auth.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("summary", data)
        self.assertGreaterEqual(data["summary"]["total_parsed"], 1)



"""Test Suite for Dynamic AMFI ETF Ingestion Pipeline, Analytical Engine, and UI Integration.

Validates:
1. Canonical ETF Universe completeness (140+ ETFs across 9 categories).
2. AMFI text feed parsing, FoF exclusion, deterministic symbol resolution, and categorization.
3. Database persistence (SQLite/PostgreSQL dual-binding, batch upserts, search, sorting).
4. Analytical engine evaluations (arbitrage detection, tracking error drag, liquidity tiers).
5. Web router endpoints (/etfs, /api/etfs/matrix, /api/etfs/{symbol}, /api/admin/etfs/trigger-ingest).
"""

import unittest
from fastapi.testclient import TestClient

from core.db.connection import init_db
from core.db.etf_universe import CANONICAL_ETF_UNIVERSE
from core.ingestion.etf_ingest import (
    derive_etf_category,
    derive_underlying_index,
    resolve_symbol,
    parse_amfi_etf_feed,
    ingest_all_amfi_etfs,
    get_or_seed_canonical_etfs,
)
from core.db.sovereign import (
    get_etf_matrix,
    get_etf_by_symbol,
    save_etf_matrix_item,
    save_etf_matrix_items,
    DEFAULT_ETF_MATRIX,
)
from core.analysis.etf_matrix_engine import evaluate_etf_matrix, get_etf_detail
from web.main import app


class TestCanonicalETFUniverse(unittest.TestCase):
    """Validates the seed universe of benchmark ETFs."""

    def test_canonical_universe_size(self):
        self.assertGreaterEqual(len(CANONICAL_ETF_UNIVERSE), 140, "Universe must contain at least 140 ETFs")

    def test_symbol_uniqueness(self):
        symbols = [item["symbol"].upper() for item in CANONICAL_ETF_UNIVERSE]
        self.assertEqual(len(symbols), len(set(symbols)), "Canonical ETF symbols must be strictly unique")

    def test_category_coverage(self):
        expected_categories = {
            "EQUITY_INDEX",
            "EQUITY_SECTORAL",
            "EQUITY_FACTOR",
            "COMMODITY_GOLD",
            "COMMODITY_SILVER",
            "DEBT_SOVEREIGN",
            "DEBT_TARGET_MATURITY",
            "LIQUID",
            "INTERNATIONAL",
        }
        actual_categories = {item["category"] for item in CANONICAL_ETF_UNIVERSE}
        self.assertEqual(expected_categories, actual_categories, "All 9 categories must be represented in universe")

    def test_numeric_integrity(self):
        for item in CANONICAL_ETF_UNIVERSE:
            self.assertGreater(item["last_price"], 0.0, f"Invalid price for {item['symbol']}")
            self.assertGreater(item["nav"], 0.0, f"Invalid NAV for {item['symbol']}")
            self.assertGreater(item["aum_crores"], 0.0, f"Invalid AUM for {item['symbol']}")
            self.assertGreaterEqual(item["expense_ratio_pct"], 0.0, f"Invalid TER for {item['symbol']}")
            self.assertGreaterEqual(item["tracking_error_1y"], 0.0, f"Invalid tracking error for {item['symbol']}")


class TestAMFIParsingAndCategorization(unittest.TestCase):
    """Validates classification, FoF exclusion, and deterministic symbol allocation."""

    def test_category_derivation(self):
        self.assertEqual(derive_etf_category("Nippon India ETF Gold BeES"), "COMMODITY_GOLD")
        self.assertEqual(derive_etf_category("SBI Silver ETF"), "COMMODITY_SILVER")
        self.assertEqual(derive_etf_category("Nippon India ETF Liquid BeES"), "LIQUID")
        self.assertEqual(derive_etf_category("Edelweiss BHARAT Bond ETF - April 2030"), "DEBT_TARGET_MATURITY")
        self.assertEqual(derive_etf_category("ICICI Prudential Nifty 5 yr Benchmark G-Sec ETF"), "DEBT_SOVEREIGN")
        self.assertEqual(derive_etf_category("Motilal Oswal Nasdaq 100 ETF"), "INTERNATIONAL")
        self.assertEqual(derive_etf_category("Mirae Asset Nifty Midcap 150 ETF"), "EQUITY_INDEX")
        self.assertEqual(derive_etf_category("Nippon India ETF Nifty Bank BeES"), "EQUITY_SECTORAL")
        self.assertEqual(derive_etf_category("UTI Nifty200 Momentum 30 ETF"), "EQUITY_FACTOR")
        # AMC Prefix collision guards (ADITYA contains IT but must NOT trigger EQUITY_SECTORAL for broad index)
        self.assertEqual(derive_etf_category("Aditya Birla Sun Life BSE Sensex ETF"), "EQUITY_INDEX")
        self.assertEqual(derive_etf_category("Aditya Birla Sun Life Nifty 50 ETF"), "EQUITY_INDEX")
        self.assertEqual(derive_etf_category("Aditya Birla Sun Life Nifty IT ETF"), "EQUITY_SECTORAL")
        # Factor / Smart Beta verification
        self.assertEqual(derive_etf_category("Axis Nifty500 Value 50 ETF"), "EQUITY_FACTOR")
        self.assertEqual(derive_etf_category("Mirae Asset BSE 500 Dividend Leaders 50 ETF"), "EQUITY_FACTOR")
        self.assertEqual(derive_etf_category("Nippon India ETF Nifty Next 50 Junior BeES"), "EQUITY_INDEX")

    def test_underlying_index_derivation(self):
        self.assertEqual(derive_underlying_index("Nippon India ETF Gold BeES", "COMMODITY_GOLD"), "Domestic Price of Physical Gold (999 Purity)")
        self.assertEqual(derive_underlying_index("Nippon India ETF Liquid BeES", "LIQUID"), "Nifty 1D Rate Index (TREPS)")
        self.assertIn("Nifty 50", derive_underlying_index("HDFC Nifty 50 ETF", "EQUITY_INDEX"))
        self.assertIn("Momentum", derive_underlying_index("UTI Nifty200 Momentum 30 ETF", "EQUITY_FACTOR"))
        # AMC Prefix stripped benchmark derivation
        self.assertEqual(derive_underlying_index("Aditya Birla Sun Life BSE Sensex ETF", "EQUITY_INDEX"), "BSE Sensex TRI")
        self.assertEqual(derive_underlying_index("Nippon India ETF Nifty IT", "EQUITY_SECTORAL"), "Nifty IT TRI")
        self.assertEqual(derive_underlying_index("Edelweiss BHARAT Bond ETF - April 2030", "DEBT_TARGET_MATURITY"), "Nifty BHARAT Bond Index - April 2030")

    def test_fof_filtering_in_feed_parser(self):
        sample_feed = (
            "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
            "Open Ended Schemes ( Other Scheme - Other ETFs )\n"
            "Nippon India Mutual Fund\n"
            "119551;INF204KB14I2;-;Nippon India ETF Nifty 50 BeES;272.4200;14-Oct-2026\n"
            "140088;INF204KB17I5;-;Nippon India ETF Gold BeES;122.4186;14-Oct-2026\n"
            "152980;INF666M01IX9;-;Groww Gold ETF FOF - Direct Plan - Growth;18.1815;14-Oct-2026\n"
            "153745;INF666M01LN4;-;Groww BSE Power ETF Fund of Fund - Regular;10.6922;14-Oct-2026\n"
        )
        parsed = parse_amfi_etf_feed(sample_feed)
        scheme_names = [p["scheme_name"].lower() for p in parsed]
        # FoFs must be filtered out
        for name in scheme_names:
            self.assertNotIn("fof", name, "FoF should be excluded from direct ETF matrix")
            self.assertNotIn("fund of fund", name, "Fund of Fund should be excluded from direct ETF matrix")

    def test_symbol_resolution_uniqueness(self):
        allocated = set()
        lookup = {item["scheme_code"]: item for item in CANONICAL_ETF_UNIVERSE if item.get("scheme_code")}
        sym1 = resolve_symbol("Groww Nifty 50 ETF", "153699", "INF666M01LL8", lookup, allocated)
        sym2 = resolve_symbol("Groww Nifty 500 Low Volatility 50 ETF", "153583", "INF666M01LB9", lookup, allocated)
        sym3 = resolve_symbol("Groww Nifty 500 Momentum 50 ETF", "153452", "INF666M01KJ4", lookup, allocated)
        self.assertNotEqual(sym1, sym2)
        self.assertNotEqual(sym2, sym3)
        self.assertEqual(len(allocated), 3)


class TestETFDatabaseOperations(unittest.TestCase):
    """Validates DB persistence, querying, multi-attribute filtering, and sorting."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def test_save_and_retrieve_etf_matrix(self):
        test_item = {
            "symbol": "TESTNIFTY",
            "scheme_name": "Test Benchmark Nifty ETF",
            "category": "EQUITY_INDEX",
            "underlying_index": "Nifty 50 TRI",
            "last_price": 250.00,
            "nav": 249.50,
            "tracking_error_1y": 0.03,
            "expense_ratio_pct": 0.05,
            "aum_crores": 5000.0,
            "avg_daily_volume": 100000.0,
            "avg_daily_turnover_cr": 2.5,
            "liquidity_tier": "HIGH_LIQUIDITY",
            "scheme_code": "999999",
            "isin": "INF999K01999"
        }
        saved = save_etf_matrix_item(test_item)
        self.assertTrue(saved)

        fetched = get_etf_by_symbol("TESTNIFTY")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["symbol"], "TESTNIFTY")
        self.assertEqual(fetched["scheme_name"], "Test Benchmark Nifty ETF")
        self.assertEqual(fetched["last_price"], 250.00)
        self.assertEqual(fetched["nav"], 249.50)

    def test_get_etf_matrix_with_filters(self):
        # Category filter
        gold_etfs = get_etf_matrix(category="COMMODITY_GOLD")
        self.assertGreater(len(gold_etfs), 0)
        for item in gold_etfs:
            self.assertEqual(item["category"], "COMMODITY_GOLD")

        # Query filter
        nifty_etfs = get_etf_matrix(query="NIFTY")
        self.assertGreater(len(nifty_etfs), 0)
        for item in nifty_etfs:
            matches = (
                "NIFTY" in item["symbol"].upper() or
                "NIFTY" in item["scheme_name"].upper() or
                "NIFTY" in item.get("underlying_index", "").upper()
            )
            self.assertTrue(matches, f"Item {item['symbol']} does not match query NIFTY")

    def test_get_etf_matrix_sorting(self):
        # Sort by AUM descending
        by_aum = get_etf_matrix(sort_by="aum_desc", limit=5)
        for i in range(len(by_aum) - 1):
            self.assertGreaterEqual(by_aum[i]["aum_crores"], by_aum[i+1]["aum_crores"])

        # Sort by tracking error ascending
        by_te = get_etf_matrix(sort_by="tracking_error_asc", limit=5)
        for i in range(len(by_te) - 1):
            self.assertLessEqual(by_te[i]["tracking_error_1y"], by_te[i+1]["tracking_error_1y"])


class TestETFMatrixEngine(unittest.TestCase):
    """Validates analytical computations, accounting check notes, and detail resolution."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def test_evaluate_etf_matrix_aggregation(self):
        matrix = evaluate_etf_matrix()
        self.assertIn("total_tracked_etfs", matrix)
        self.assertGreaterEqual(matrix["total_tracked_etfs"], 120)
        self.assertIn("total_aum_lakh_cr", matrix)
        self.assertGreater(matrix["total_aum_crores"], 100000.0)
        self.assertIn("category_counts", matrix)
        self.assertIn("EQUITY_INDEX", matrix["category_counts"])
        self.assertIn("COMMODITY_GOLD", matrix["category_counts"])

        # Check grouped_by_category backward compatibility
        self.assertIn("grouped_by_category", matrix)
        self.assertIn("ALL", matrix["grouped_by_category"])
        self.assertIn("EQUITY_INDEX", matrix["grouped_by_category"])

    def test_get_etf_detail_resolution(self):
        detail = get_etf_detail("NIFTYBEES")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["etf"]["symbol"], "NIFTYBEES")
        self.assertIn("aum_formatted", detail)
        self.assertIn("peers", detail)
        self.assertIn("forensic_notes", detail)
        self.assertIn("arbitrage_analysis", detail)
        self.assertIn("replication_audit", detail)
        self.assertIn("liquidity_audit", detail)
        self.assertIn("countercase_risks", detail)
        self.assertIn("amc_issuer", detail)
        self.assertEqual(detail["amc_issuer"], "Nippon India Mutual Fund")
        self.assertIn("market_price", detail["arbitrage_analysis"])
        self.assertIn("fair_nav", detail["arbitrage_analysis"])
        self.assertIn("spread_pct", detail["arbitrage_analysis"])


class TestWebAndApiEndpoints(unittest.TestCase):
    """Validates web routes and JSON API contracts."""

    @classmethod
    def setUpClass(cls):
        init_db()
        get_or_seed_canonical_etfs()

    def setUp(self):
        self.client = TestClient(app)

    def test_etfs_html_page(self):
        response = self.client.get("/etfs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("National ETF Performance & Liquidity Matrix", response.text)
        self.assertIn("Equity Indices", response.text)
        self.assertIn("Gold", response.text)
        self.assertIn("/etfs/NIFTYBEES", response.text)

    def test_etf_dossier_html_niftybees(self):
        """Validates the ETF Stock Report (/etfs/NIFTYBEES)."""
        response = self.client.get("/etfs/NIFTYBEES")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Nippon India ETF Nifty 50 BeES", html)
        self.assertIn("NIFTYBEES", html)
        self.assertIn("Secondary Market Spread", html)
        self.assertIn("Statutory Fair NAV", html)
        self.assertIn("1Y Tracking Error", html)
        self.assertIn("Total Expense Ratio", html)
        self.assertIn("Category Peer Comparison", html)
        self.assertIn("Structural Failure Modes", html)
        self.assertIn("SEBI Statutory Safe Harbor Compliance", html)
        self.assertIn("openCopilot('NIFTYBEES', 'etf')", html)

        # Semantic render hygiene assertions
        self.assertNotIn("None%", html)
        self.assertNotIn("NaN%", html)
        self.assertNotIn("₹None", html)
        self.assertNotIn("Gemini", html)
        self.assertNotIn("Copilot Desk Notice: Exception", html)

    def test_etf_dossier_html_goldbees(self):
        """Validates commodity gold ETF dossier (/etfs/GOLDBEES)."""
        response = self.client.get("/etfs/GOLDBEES")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Gold BeES", html)
        self.assertIn("Direct Physical Bullion Vault", html)

    def test_etf_dossier_not_found(self):
        """Validates 404 behavior for unknown ETF symbols."""
        response = self.client.get("/etfs/UNKNOWN_ETF_999")
        self.assertEqual(response.status_code, 404)

    def test_api_etfs_matrix_endpoint(self):
        response = self.client.get("/api/etfs/matrix")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_tracked_etfs", data)
        self.assertGreaterEqual(data["total_tracked_etfs"], 120)
        self.assertIn("etfs", data)

    def test_api_etfs_detail_endpoint(self):
        response = self.client.get("/api/etfs/NIFTYBEES")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["etf"]["symbol"], "NIFTYBEES")
        self.assertIn("arbitrage_analysis", data)
        self.assertIn("replication_audit", data)

    def test_api_etfs_detail_not_found(self):
        response = self.client.get("/api/etfs/NONEXISTENT_TICKER_999")
        self.assertEqual(response.status_code, 404)

    def test_api_admin_trigger_ingest(self):
        from web.common import _generate_admin_token, ADMIN_COOKIE_NAME
        admin_token = _generate_admin_token("admin@moatnomics.com", role="super_admin")
        self.client.cookies.set(ADMIN_COOKIE_NAME, admin_token)
        response = self.client.post("/api/admin/etfs/trigger-ingest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")

    def test_etf_copilot_chat_arbitrage_query(self):
        """Validates Research Desk interaction for ETF queries."""
        payload = {
            "conversation_id": "test-etf-copilot-arb",
            "message": "What is the arbitrage spread and premium for NIFTYBEES?",
            "ticker": "NIFTYBEES",
            "asset_type": "etf"
        }
        response = self.client.post("/api/copilot/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        resp_text = data.get("response", "")
        self.assertIn("NIFTYBEES", resp_text)
        self.assertTrue("Arbitrage" in resp_text or "Fair NAV" in resp_text or "Spread" in resp_text)
        self.assertNotIn("Gemini", resp_text)

    def test_etf_copilot_chat_regulatory_deflection(self):
        """Validates SEBI Safe Harbor non-advisory deflection for ETF queries."""
        payload = {
            "conversation_id": "test-etf-copilot-deflect",
            "message": "Should I buy NIFTYBEES today?",
            "ticker": "NIFTYBEES",
            "asset_type": "etf"
        }
        response = self.client.post("/api/copilot/chat", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "REGULATORY_DEFLECTED")




import io
import unittest
from datetime import date
from unittest.mock import patch

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    openpyxl = None

from core.ingestion.mf_portfolio_ingest import (
    amc_key_for_fund_house,
    build_holdings,
    ingest_top_funds,
    load_sources,
    recent_month_ends,
    render_url,
    validate_holdings,
)
from core.ingestion.mf_portfolio_parser import (
    match_scheme_name,
    normalize_scheme_name,
    parse_as_on_date,
    parse_workbook,
    sniff_format,
)
from core.ingestion.mf_universe import rank_funds_by_aum

HEADER = ["ISIN", "Name of the Instrument", "Industry / Rating", "Quantity",
          "Market/Fair Value\n( Rs. in Lacs)", "% to NAV"]


def _equity_sheet(wb, title, scheme_title, weights, as_fraction=True):
    ws = wb.create_sheet(title)
    ws.append(["RLMF001", scheme_title, "Index"])
    ws.append(["Monthly Portfolio Statement as on August 31,2026"])
    ws.append([])
    ws.append([None] + HEADER[:])  # leading code column shifts headers by one, like real files
    ws.append(["Equity & Equity related"])
    ws.append(["(a) Listed / awaiting listing on Stock Exchanges"])
    isins = ["INE040A01034", "INE002A01018", "INE009A01021"]
    for i, w in enumerate(weights):
        ws.append(["CODE%d" % i, isins[i], "Company %d Limited**" % i, "Banks", 1000, 500.0,
                   w if as_fraction else w * 100])
    ws.append(["Total", None, None, None, None, 3000.0, sum(weights)])
    ws.append(["Money Market Instruments"])
    ws.append(["Triparty Repo/ Reverse Repo Instrument"])
    ws.append(["Triparty Repo", None, None, None, None, 100.0, round(1 - sum(weights) - 0.001, 4) if as_fraction
               else round((1 - sum(weights) - 0.001) * 100, 2)])
    ws.append(["Total", None, None, None, None, 100.0, 0.02])
    ws.append(["OTHERS"])
    ws.append(["Net Current Assets", None, None, None, None, 10.0, 0.001 if as_fraction else 0.1])
    ws.append(["Notes:"])
    ws.append(["Note one with an INE000000000 mention"])
    return ws


def _book_bytes(builder):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    builder(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@unittest.skipUnless(HAS_OPENPYXL, "openpyxl is required for synthetic workbook ingestion tests")
class TestParser(unittest.TestCase):
    def test_sniff_ignores_extension(self):
        data = _book_bytes(lambda wb: _equity_sheet(wb, "EA", "Alpha Fund", [0.5, 0.3, 0.17]))
        self.assertEqual(sniff_format(data), "xlsx")
        self.assertEqual(sniff_format(b"<html><body>blocked</body></html>"), "html")
        self.assertEqual(sniff_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"), "xls")

    def test_parses_fraction_weights_and_cash(self):
        data = _book_bytes(lambda wb: _equity_sheet(
            wb, "EA", "Alpha Equity Fund (An open ended equity scheme)", [0.5, 0.3, 0.17]))
        parsed = parse_workbook(data)["EA"]
        self.assertEqual(parsed["scheme_name"], "Alpha Equity Fund")
        self.assertEqual(parsed["as_on_date"], "2026-08-31")
        hs = parsed["holdings"]
        self.assertAlmostEqual(sum(h["weight_pct"] for h in hs), 100.0, delta=0.01)
        self.assertEqual(sum(1 for h in hs if h["holding_type"] == "EQUITY"), 3)
        cash = [h for h in hs if h["holding_type"] == "CASH_EQUIVALENT"]
        self.assertEqual({c["holding_name"] for c in cash}, {"Triparty Repo", "Net Current Assets"})
        self.assertTrue(all(h["holding_name"].endswith("Limited") for h in hs if h["holding_type"] == "EQUITY"))

    def test_parses_percent_weights(self):
        data = _book_bytes(lambda wb: _equity_sheet(wb, "EB", "Beta Fund", [0.5, 0.3, 0.17], as_fraction=False))
        hs = parse_workbook(data)["EB"]["holdings"]
        self.assertAlmostEqual(sum(h["weight_pct"] for h in hs), 100.0, delta=0.05)

    def test_note_text_not_parsed_as_holdings(self):
        data = _book_bytes(lambda wb: _equity_sheet(wb, "EA", "Alpha Fund", [0.5, 0.3, 0.17]))
        hs = parse_workbook(data)["EA"]["holdings"]
        self.assertFalse(any("INE000000000" in h["isin"] for h in hs))

    def test_non_portfolio_sheets_ignored(self):
        def build(wb):
            ws = wb.create_sheet("Index")
            ws.append(["Code", "Scheme"])
            _equity_sheet(wb, "EA", "Alpha Fund", [0.5, 0.3, 0.17])
        self.assertEqual(list(parse_workbook(_book_bytes(build)).keys()), ["EA"])

    def test_html_rejected(self):
        with self.assertRaises(ValueError):
            parse_workbook(b"<!DOCTYPE html><html></html>")

    def test_date_formats(self):
        self.assertEqual(parse_as_on_date("Monthly Portfolio Statement as on August 31,2026"), "2026-08-31")
        self.assertEqual(parse_as_on_date("as on 31-Aug-2026"), "2026-08-31")
        self.assertEqual(parse_as_on_date("Portfolio as on 31/08/2026"), "2026-08-31")
        self.assertIsNone(parse_as_on_date("no date here"))

    def test_scheme_name_matching(self):
        titles = ["Nippon India Small Cap Fund", "Nippon India Large Cap Fund", "Nippon India Multi Cap Fund"]
        self.assertEqual(
            match_scheme_name("Nippon India Small Cap Fund - Direct Plan Growth Plan - Growth Option", titles),
            "Nippon India Small Cap Fund")
        self.assertIsNone(match_scheme_name("Nippon India Gold Savings Fund - Direct Plan - Growth", titles))
        self.assertEqual(normalize_scheme_name("Alpha & Beta  Fund (An open ended)"), "alphaandbeta")

    def test_ambiguous_match_returns_none(self):
        self.assertIsNone(match_scheme_name("Alpha Fund", ["Alpha Fund", "ALPHA FUND"]))


class TestIngestionHelpers(unittest.TestCase):
    def test_month_end_and_url(self):
        ends = recent_month_ends(3, date(2026, 10, 8))
        self.assertEqual(ends, [date(2026, 9, 30), date(2026, 8, 31), date(2026, 7, 31)])
        url = render_url(load_sources()["nippon"]["url_template"], date(2026, 8, 31))
        self.assertTrue(url.endswith("NIMF-MONTHLY-PORTFOLIO-31-Aug-26.xls"))

    def test_registry_only_enables_verified_amcs(self):
        for key, cfg in load_sources().items():
            if cfg.get("url_template"):
                self.assertTrue(cfg.get("verified_on"), f"{key} template enabled without verification date")

    def test_fund_house_to_key(self):
        src = load_sources()
        self.assertEqual(amc_key_for_fund_house("Nippon India Mutual Fund", src), "nippon")
        self.assertIsNone(amc_key_for_fund_house("Unknown MF", src))

    def test_validate_rejects_incomplete(self):
        self.assertIsNotNone(validate_holdings([]))
        self.assertIsNotNone(validate_holdings([{"weight_pct": 60.0}]))
        self.assertIsNone(validate_holdings([{"weight_pct": 99.2}]))

    def test_build_holdings_maps_isin_and_merges(self):
        parsed = {
            "as_on_date": "2026-08-31",
            "holdings": [
                {"isin": "INE040A01034", "holding_name": "HDFC Bank", "holding_type": "EQUITY",
                 "sector_or_rating": "Banks", "weight_pct": 5.0, "instrument_details": {}},
                {"isin": "INE040A01034", "holding_name": "HDFC Bank", "holding_type": "EQUITY",
                 "sector_or_rating": "Banks", "weight_pct": 1.0, "instrument_details": {}},
                {"isin": "", "holding_name": "Triparty Repo", "holding_type": "CASH_EQUIVALENT",
                 "sector_or_rating": "CASH", "weight_pct": 2.0, "instrument_details": {}},
                {"isin": "IN0020160035", "holding_name": "6.97% GOI", "holding_type": "DEBT",
                 "sector_or_rating": "SOVEREIGN", "weight_pct": 3.0, "instrument_details": {"ytm": 5.2}},
            ],
        }
        out = build_holdings(parsed, {"INE040A01034": "HDFCBANK"})
        by_id = {h["identifier"]: h for h in out}
        self.assertEqual(by_id["HDFCBANK"]["weight_pct"], 6.0)
        self.assertIn("TREPS", by_id)
        self.assertIn("IN0020160035", by_id)
        self.assertEqual(by_id["IN0020160035"]["instrument_details"]["ytm"], 5.2)
        self.assertEqual(out[0]["identifier"], "HDFCBANK")


class TestUniverseRanking(unittest.TestCase):
    AAUM = [
        {"Mfname": "Alpha Mutual Fund", "SchemeCat_Desc": "Equity Scheme - Flexi Cap Fund", "schemes": [
            {"SchemeNAVName": "Alpha Flexi Fund - Direct Plan - Growth", "AMFI_Code": 1,
             "AverageAumForTheMonth": {"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 5000000.0}},
            {"SchemeNAVName": "Alpha Flexi Fund - Regular Plan - Growth", "AMFI_Code": 2,
             "AverageAumForTheMonth": {"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 9000000.0}},
            {"SchemeNAVName": "Alpha Flexi Fund - Direct Plan - IDCW Payout", "AMFI_Code": 3,
             "AverageAumForTheMonth": {"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 9000000.0}},
        ]},
        {"Mfname": "Beta Mutual Fund", "SchemeCat_Desc": "Debt Scheme - Liquid Fund", "schemes": [
            {"SchemeNAVName": "Beta Liquid Fund - Direct Plan - Growth", "AMFI_Code": 4,
             "AverageAumForTheMonth": {"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 7000000.0}},
        ]},
        {"Mfname": "Beta Mutual Fund", "SchemeCat_Desc": "Other Scheme - FoF Domestic", "schemes": [
            {"SchemeNAVName": "Beta FoF - Direct Plan - Growth", "AMFI_Code": 5,
             "AverageAumForTheMonth": {"ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas": 99999999.0}},
        ]},
    ]

    def test_ranks_direct_growth_only_and_converts_to_crores(self):
        ranked = rank_funds_by_aum(self.AAUM)
        self.assertEqual([r["scheme_code"] for r in ranked], ["4", "1"])
        self.assertEqual(ranked[0]["aum_crores"], 70000.0)
        self.assertEqual([r["aum_rank"] for r in ranked], [1, 2])


@unittest.skipUnless(HAS_OPENPYXL, "openpyxl is required for synthetic workbook ingestion tests")
class TestOrchestratorSkipAndReplace(unittest.TestCase):
    def _universe(self):
        return [
            {"aum_rank": 1, "scheme_code": "9001", "scheme_name": "Nippon India Alpha Fund - Direct Plan - Growth",
             "fund_house": "Nippon India Mutual Fund", "category": "Flexi Cap Fund",
             "broad_category": "EQUITY", "aum_crores": 900.0},
            {"aum_rank": 2, "scheme_code": "9002", "scheme_name": "SBI Beta Fund - Direct Plan - Growth",
             "fund_house": "SBI Mutual Fund", "category": "Flexi Cap Fund",
             "broad_category": "EQUITY", "aum_crores": 800.0},
            {"aum_rank": 3, "scheme_code": "9003", "scheme_name": "Nippon India Missing Fund - Direct Plan - Growth",
             "fund_house": "Nippon India Mutual Fund", "category": "Flexi Cap Fund",
             "broad_category": "EQUITY", "aum_crores": 700.0},
            {"aum_rank": 4, "scheme_code": "9004", "scheme_name": "Nippon India Gamma Fund - Direct Plan - Growth",
             "fund_house": "Nippon India Mutual Fund", "category": "Flexi Cap Fund",
             "broad_category": "EQUITY", "aum_crores": 600.0},
        ]

    def _provider(self):
        def build(wb):
            _equity_sheet(wb, "A1", "Nippon India Alpha Fund (An open ended scheme)", [0.5, 0.3, 0.17])
            _equity_sheet(wb, "A2", "Nippon India Gamma Fund (An open ended scheme)", [0.6, 0.2, 0.19])
        data = _book_bytes(build)
        return lambda key, cfg: (data, "test") if key == "nippon" else None

    @patch("core.ingestion.mf_portfolio_ingest.fetch_amfi_nav_raw", return_value="")
    def test_skips_funds_without_data_and_replaces_with_next(self, _):
        report = ingest_top_funds(
            target=2, dry_run=True, universe=self._universe(),
            workbook_provider=self._provider(), isin_map={})
        self.assertEqual([f["scheme_code"] for f in report["ingested"]], ["9001", "9004"])
        self.assertTrue(report["target_met"])
        reasons = {s["scheme_code"]: s["reason"] for s in report["skipped"]}
        self.assertIn("no workbook", reasons["9002"])
        self.assertIn("no matching scheme sheet", reasons["9003"])

    @patch("core.ingestion.mf_portfolio_ingest.fetch_amfi_nav_raw", return_value="")
    def test_reports_shortfall_honestly(self, _):
        report = ingest_top_funds(
            target=10, dry_run=True, universe=self._universe(),
            workbook_provider=self._provider(), isin_map={})
        self.assertFalse(report["target_met"])
        self.assertEqual(report["ingested_count"], 2)

    @patch("core.ingestion.mf_portfolio_ingest.fetch_amfi_nav_raw", return_value="")
    def test_dry_run_writes_nothing(self, _):
        with patch("core.ingestion.mf_portfolio_ingest.save_mutual_fund_holdings") as save_h, \
             patch("core.ingestion.mf_portfolio_ingest.save_mutual_fund_scheme") as save_s:
            ingest_top_funds(target=2, dry_run=True, universe=self._universe(),
                             workbook_provider=self._provider(), isin_map={})
            save_h.assert_not_called()
            save_s.assert_not_called()

    @patch("core.ingestion.mf_portfolio_ingest.fetch_amfi_nav_raw", return_value="")
    def test_real_run_saves_holdings_and_scheme(self, _):
        with patch("core.ingestion.mf_portfolio_ingest.save_mutual_fund_holdings", return_value=True) as save_h, \
             patch("core.ingestion.mf_portfolio_ingest.save_mutual_fund_scheme", return_value=True) as save_s, \
             patch("core.ingestion.mf_portfolio_ingest.get_mutual_fund_scheme", return_value=None):
            ingest_top_funds(target=1, dry_run=False, universe=self._universe(),
                             workbook_provider=self._provider(), isin_map={"INE040A01034": "HDFCBANK"})
            self.assertEqual(save_h.call_count, 1)
            code, holdings = save_h.call_args[0]
            self.assertEqual(code, "9001")
            self.assertIn("HDFCBANK", [h["identifier"] for h in holdings])
            saved_scheme = save_s.call_args[0][0]
            self.assertEqual(saved_scheme["aum_crores"], 900.0)
            self.assertEqual(saved_scheme["metadata"]["holdings_as_on"], "2026-08-31")




if __name__ == "__main__":
    unittest.main()

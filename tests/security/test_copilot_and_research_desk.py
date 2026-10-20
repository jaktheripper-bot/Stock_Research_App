"""
tests/security/test_copilot_and_research_desk.py
=================================================
Consolidated Research Desk, Autonomous Agents & Source-Grounded Guardrails:
1. Research Desk multi-turn chat, multi-pillar intent classification, and fallback
2. Admin Copilot thread resolution, action execution, and credit grants
3. Sitewide autonomous agent runners and background daemons
4. Zero-hallucination contact, address, entity and SEBI non-registration guards
"""
import os
os.environ["TESTING"] = "1"

import re
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from web.main import app


"""Unit tests for Research Desk Input Qualification, Open-Ended Synthesis, and Tier Gating."""

import os
import unittest
import asyncio
from fastapi.testclient import TestClient

from web.main import app, init_db
from core.agents.copilot.research_desk import (
    check_input_qualification,
    is_input_qualified,
    detect_forbidden_intent,
    process_research_desk_turn,
    _resolve_dynamic_entity_override,
    _answer_from_local_dossier_index
)


class TestResearchDeskEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        os.environ["AUDIT_RECURSION_GUARD"] = "1"
        init_db()
        cls.client = TestClient(app)

    def test_input_qualification_gibberish_rejection(self):
        """Verifies that meaningless keyboard mash, noise, and spam are rejected."""
        gibberish_samples = [
            "asdfghjkl",
            "qwertyuiop",
            "zzzzzzzz",
            "????",
            ".....",
            "!@#$%",
            "bcdfghjk",
            "12345678",
            "blahblah",
            "testtest",
            "q",
            "x"
        ]
        for sample in gibberish_samples:
            intercept = check_input_qualification(sample, asset_class="EQUITY", ticker="INFY")
            self.assertIsNotNone(intercept, f"Expected '{sample}' to be intercepted as unqualified input.")
            self.assertEqual(intercept["status"], "INPUT_UNQUALIFIED")
            self.assertIn("Input Not Recognized", intercept["response"])
            self.assertIn("What stood out", intercept["response"])

    def test_input_qualification_greetings(self):
        """Verifies that casual greetings receive friendly onboarding orientation."""
        greeting_samples = ["hi", "hello", "hey", "good morning", "ping"]
        for sample in greeting_samples:
            intercept = check_input_qualification(sample, asset_class="EQUITY", ticker="INFY")
            self.assertIsNotNone(intercept, f"Expected '{sample}' to be intercepted as greeting.")
            self.assertEqual(intercept["status"], "GREETING")
            self.assertIn("Welcome to the Research Desk", intercept["response"])

    def test_input_qualification_allows_valid_financial_queries(self):
        """Verifies that valid financial terms and questions are never falsely rejected."""
        valid_samples = [
            "what shocked you?",
            "summarize the bear thesis",
            "what is the PE ratio?",
            "reverse dcf",
            "explain the economic moat",
            "TCS",
            "NCD",
            "SDI",
            "ROCE",
            "how is the balance sheet solvency?"
        ]
        for sample in valid_samples:
            intercept = check_input_qualification(sample, asset_class="EQUITY", ticker="INFY")
            self.assertIsNone(intercept, f"Valid query '{sample}' should not be intercepted as gibberish.")

    def test_input_qualification_contextual_numbers_and_shorthand(self):
        """Verifies numbers with context (10000, 50000 cr) and shorthands (bps, ROE?, WALE, LTV) are allowed."""
        valid_contextual_samples = [
            "invest 10000 in reliance",
            "what is 50000 cr mcap?",
            "ROE?",
            "150 bps spread",
            "WALE",
            "LTV",
            "NDCF",
            "30% tax slab"
        ]
        for sample in valid_contextual_samples:
            self.assertTrue(is_input_qualified(sample), f"'{sample}' should be qualified via is_input_qualified.")
            self.assertTrue(check_input_qualification(sample), f"'{sample}' should be qualified via boolean check_input_qualification.")
            intercept = check_input_qualification(sample, asset_class="EQUITY", ticker="INFY")
            self.assertIsNone(intercept, f"Valid contextual query '{sample}' should not be intercepted.")

        # Test single-argument boolean check for invalid / greeting input
        for sample in ["asdfghjkl", "blahblah", "hi", "hello", "", "12345678"]:
            self.assertFalse(check_input_qualification(sample), f"'{sample}' should return False via boolean check_input_qualification.")

    def test_equity_open_ended_what_shocked_you(self):
        """Verifies that 'what shocked you?' yields real contextual anomalies, not a canned menu."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-OPEN-ENDED-SHOCK",
                user_message="What shocked you during the research on this stock?",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Key Forensic Surprises & Structural Red Flags", resp)
            self.assertNotIn("Select a diagnostic pillar to drill into:", resp)
            # Free tier distinction notice must be present
            self.assertIn("Free Tier", resp)

        asyncio.run(_run())

    def test_equity_open_ended_bear_thesis(self):
        """Verifies that 'summarize the bear thesis' yields structured downside vectors."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-OPEN-ENDED-BEAR",
                user_message="Summarize the bear thesis for this stock.",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Bear Thesis Summary", resp)
            self.assertIn("Multiple De-Rating", resp)
            self.assertIn("Free Tier", resp)

        asyncio.run(_run())

    def test_equity_open_ended_bull_thesis(self):
        """Verifies that 'summarize the bull thesis' yields structural compounding vectors."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-OPEN-ENDED-BULL",
                user_message="Summarize the bull thesis and upside catalysts.",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Bull Thesis Summary", resp)
            self.assertIn("Competitive Moat", resp)
            self.assertIn("Free Tier", resp)

    def test_tier_distinction_notice_unlocked_vs_free(self):
        """Verifies that unlocked / pro users receive verified Pro notice while free users get Free Tier notice."""
        async def _run():
            # Free user
            res_free = await process_research_desk_turn(
                conversation_id="TEST-TIER-FREE",
                user_message="Explain the balance sheet solvency.",
                ticker="INFY",
                deep_dive_unlocked=False,
                is_subscriber=False
            )
            self.assertIn("Free Tier", res_free["response"])

            # Unlocked report user
            res_unlocked = await process_research_desk_turn(
                conversation_id="TEST-TIER-UNLOCKED",
                user_message="Explain the balance sheet solvency.",
                ticker="INFY",
                deep_dive_unlocked=True,
                is_subscriber=False
            )
            self.assertIn("Your entitlement is verified (Unlocked/Pro)", res_unlocked["response"])

            # Subscriber user
            res_sub = await process_research_desk_turn(
                conversation_id="TEST-TIER-SUB",
                user_message="Explain the balance sheet solvency.",
                ticker="INFY",
                deep_dive_unlocked=False,
                is_subscriber=True
            )
            self.assertIn("Your entitlement is verified (Unlocked/Pro)", res_sub["response"])

        asyncio.run(_run())

    def test_mutual_fund_open_ended_shock(self):
        """Verifies that mutual fund open-ended questions evaluate fee drag & active share without equity jargon."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-MF-SHOCK",
                user_message="What shocked you about this fund?",
                ticker="PPFAS_FLEXICAP_DIR",
                asset_type="mutual_fund",
                deep_dive_unlocked=False
            )
            resp = res["response"]
            self.assertIn("Key Look-Through Surprises & Red Flags", resp)
            self.assertNotIn("company's Margin of Safety", resp)

        asyncio.run(_run())

    def test_corporate_debt_open_ended_shock(self):
        """Verifies that debt open-ended questions evaluate contagion & covenants without equity jargon."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-DEBT-SHOCK",
                user_message="What stood out in this bond?",
                ticker="INE002A08012",
                asset_type="corporate_debt",
                deep_dive_unlocked=False
            )
            resp = res["response"]
            self.assertIn("Key Credit Surprises & Solvency Flags", resp)
            self.assertNotIn("Trailing P/E", resp)

    def test_api_copilot_chat_gibberish_rejection(self):
        """Verifies REST API intercepts gibberish with INPUT_UNQUALIFIED status."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-API-GIBBERISH-101",
            "message": "asdfghjkl",
            "ticker": "INFY"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "INPUT_UNQUALIFIED")
        self.assertIn("Input Not Recognized", data.get("response"))

    def test_api_copilot_chat_greeting(self):
        """Verifies REST API responds politely to greetings with GREETING status."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-API-GREETING-101",
            "message": "hello",
            "ticker": "INFY"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "GREETING")
        self.assertIn("Welcome to the Research Desk", data.get("response"))


    def test_resolve_dynamic_entity_override(self):
        """Verifies mid-conversation ticker switching across uppercase tokens and natural language phrases."""
        # 1. Uppercase token override
        new_ticker, asset = _resolve_dynamic_entity_override("What about INFY?", "TCS", "EQUITY")
        self.assertEqual(new_ticker, "INFY")
        self.assertEqual(asset, "EQUITY")

        # 2. Lowercase natural language override
        new_ticker, asset = _resolve_dynamic_entity_override("switch to Infosys", "TCS", "EQUITY")
        self.assertEqual(new_ticker, "INFY")
        self.assertEqual(asset, "EQUITY")

        # 3. Stopword preservation (no false switch on acronyms or verbs)
        for non_ticker_query in ["What is the PE ratio?", "Explain the DCF model", "Where should we start?", "Check the balance sheet"]:
            curr_t, curr_a = _resolve_dynamic_entity_override(non_ticker_query, "TCS", "EQUITY")
            self.assertEqual(curr_t, "TCS", f"Query '{non_ticker_query}' should NOT override ticker.")
            self.assertEqual(curr_a, "EQUITY")

        # 4. Empty or missing message
        curr_t, curr_a = _resolve_dynamic_entity_override("", "TCS", "EQUITY")
        self.assertEqual(curr_t, "TCS")

    def test_answer_from_local_dossier_index(self):
        """Verifies zero-token local pillar and valuation radar metric retrieval for equities."""
        mock_report = {
            "ticker": "INFY",
            "company_name": "Infosys Ltd",
            "baseline_price": 1500.0,
            "baseline_pe": 25.0,
            "report_text": """
# Equity Research Report: Infosys Ltd (INFY)

## Pillar 01: Macro & Regulatory Exposure
Macroeconomic environment remains resilient across North America and Europe. RBI policies and currency movements support exports.

## Pillar 02: Competitive Moat & Industry Positioning
Infosys possesses a Wide economic moat anchored in high client switching costs, proprietary delivery platforms, and specialized digital transformation capabilities.

## Pillar 03: Promoter Quality & Fundamental Health
Clean corporate governance with unencumbered promoter holdings and conservative capital allocation.

## Pillar 04: Earnings & Margin Diagnostic
Operating margins remain protected within the 21.0% to 23.0% band. Margin compression in recent quarters reflects transitory wage hikes rather than structural impairment.

## Pillar 05: Valuation & Margin of Safety
Trading at a trailing P/E of 25.0x against historical 5-year median of 27.5x, offering favorable risk-reward asymmetry and margin of safety.

## Pillar 06: Technical & Momentum Overlay
Consolidating above 200-day exponential moving average.

## Pillar 07: SEBI BRSR & ESG Scorecard
Ranked in top decile of ESG and BRSR disclosure transparency with zero major regulatory non-compliance citations.
"""
        }
        fund = {"current_price": 1500.0, "pe_ratio": 25.0, "eps": 60.0, "short_name": "Infosys Ltd"}

        # 1. Valuation multiples / P/E query
        ans_val = _answer_from_local_dossier_index("INFY", "EQUITY", "what is the PE ratio and valuation multiple?", mock_report, fund)
        self.assertIsNotNone(ans_val)
        self.assertIn("Valuation & Multiples Diagnostic", ans_val)
        self.assertIn("Current Market Price", ans_val)
        self.assertIn("Pillar 05", ans_val)

        # 2. Business model & moat query
        ans_moat = _answer_from_local_dossier_index("INFY", "EQUITY", "explain the business model and competitive moat", mock_report, fund)
        self.assertIsNotNone(ans_moat)
        self.assertIn("Competitive Moat & Industry Positioning", ans_moat)
        self.assertIn("Pillar 02", ans_moat)

        # 3. Earnings & margins query
        ans_earn = _answer_from_local_dossier_index("INFY", "EQUITY", "how are quarterly earnings and margins?", mock_report, fund)
        self.assertIsNotNone(ans_earn)
        self.assertIn("Earnings & Margin Diagnostic", ans_earn)
        self.assertIn("Pillar 04", ans_earn)

        # 4. Macro query
        ans_macro = _answer_from_local_dossier_index("INFY", "EQUITY", "what are the macro and tariff risks?", mock_report, fund)
        self.assertIsNotNone(ans_macro)
        self.assertIn("Macro & Regulatory Exposure", ans_macro)
        self.assertIn("Pillar 01", ans_macro)

        # 5. ESG query
        ans_esg = _answer_from_local_dossier_index("INFY", "EQUITY", "what is the ESG / BRSR score?", mock_report, fund)
        self.assertIsNotNone(ans_esg)
        self.assertIn("SEBI BRSR & ESG Scorecard", ans_esg)
        self.assertIn("Pillar 07", ans_esg)

        # 6. Unmatched query or non-equity asset class returns None
        self.assertIsNone(_answer_from_local_dossier_index("INFY", "MUTUAL_FUND", "what is the PE ratio?", mock_report, fund))
        self.assertIsNone(_answer_from_local_dossier_index("INFY", "EQUITY", "unmatched random prompt", mock_report, fund))
        self.assertIsNone(_answer_from_local_dossier_index(None, "EQUITY", "what is the PE ratio?", mock_report, fund))

    def test_reverse_dcf_and_quick_chips_not_hijacked_by_pillar_04(self):
        """Regression test (WS1.4): Reverse DCF Implied Growth and quick-chips must not get hijacked by Pillar 04."""
        from unittest.mock import patch
        from core.agents.copilot.research_desk import build_equity_deterministic_response

        mock_7pillar_report = {
            "ticker": "INFY",
            "short_name": "Infosys Ltd",
            "company_name": "Infosys Ltd",
            "baseline_price": 1500.0,
            "baseline_pe": 25.0,
            "baseline_mcap": 620000.0,
            "report_text": (
                "## Pillar 01: Macro & Regulatory Exposure\nMacro context.\n\n"
                "## Pillar 02: Competitive Moat & Industry Positioning\nWide moat.\n\n"
                "## Pillar 03: Promoter Quality & Fundamental Health\nClean governance.\n\n"
                "## Pillar 04: Earnings & Margin Diagnostic\nOperating margins are 21%.\n\n"
                "## Pillar 05: Valuation & Margin of Safety\nTrading at 25x P/E.\n\n"
                "## Pillar 06: Technical & Momentum Overlay\nAbove 50-DMA.\n\n"
                "## Pillar 07: SEBI BRSR & ESG Scorecard\nTop decile BRSR.\n"
            ),
        }
        fund = {"current_price": 1500.0, "pe_ratio": 25.0, "eps": 60.0, "short_name": "Infosys Ltd"}

        # 1. Local dossier index must return None (deferring to dedicated Reverse DCF / Forensic builders)
        for chip_prompt in [
            "What implied growth rate is priced into current CMP based on Reverse DCF?",
            "What implied FCF growth rate is currently priced into the stock's Reverse DCF?",
            "How sensitive is the Reverse DCF valuation to hurdle rate assumptions?",
            "Are there any forensic accounting or earnings manipulation red flags?",
            "Identify the top 3 structural risks that could permanently impair business earnings.",
        ]:
            self.assertIsNone(
                _answer_from_local_dossier_index("INFY", "EQUITY", chip_prompt, mock_7pillar_report, fund),
                f"Local dossier index hijacked specialized prompt: '{chip_prompt}'"
            )

        # 2. Full process_research_desk_turn with 7-pillar report in DB must route Reverse DCF chip to Reverse DCF
        async def _run():
            with patch("core.db.reports.get_report_by_ticker_sync", return_value=mock_7pillar_report):
                # With explicit section="reverse_dcf"
                res_chip = await process_research_desk_turn(
                    conversation_id="TEST-WS14-CHIP",
                    user_message="What implied growth rate is priced into current CMP based on Reverse DCF?",
                    ticker="INFY",
                    asset_type="equity",
                    section="reverse_dcf",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", res_chip["response"])
                self.assertIn("Implied FCF Growth Priced In", res_chip["response"])
                self.assertNotIn("Earnings & Margin Diagnostic", res_chip["response"])

                # Without section parameter (natural-language Reverse DCF question)
                res_nl = await process_research_desk_turn(
                    conversation_id="TEST-WS14-NL",
                    user_message="What implied FCF growth rate is currently priced into the stock's Reverse DCF?",
                    ticker="INFY",
                    asset_type="equity",
                    deep_dive_unlocked=False,
                )
                self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", res_nl["response"])
                self.assertNotIn("Earnings & Margin Diagnostic", res_nl["response"])

                # Hurdle rate sensitivity chip
                res_hurdle = await process_research_desk_turn(
                    conversation_id="TEST-WS14-HURDLE",
                    user_message="How sensitive is the Reverse DCF valuation to hurdle rate assumptions?",
                    ticker="INFY",
                    asset_type="equity",
                    section="reverse_dcf",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", res_hurdle["response"])
                self.assertNotIn("Valuation & Multiples Diagnostic", res_hurdle["response"])

        asyncio.run(_run())

    def test_single_number_and_conversational_followups_not_rejected(self):
        """Verifies single-number follow-ups ('10000', '30%', '10y', '5L') and conversational replies pass qualification while digit mash fails."""
        for valid_input in ["10000", "50,000", "30%", "12.5%", "10y", "15yr", "5L", "10Cr", "₹25,000", "yes", "sure", "ok", "why?", "elaborate"]:
            self.assertTrue(
                is_input_qualified(valid_input),
                f"Expected '{valid_input}' to be qualified as a valid follow-up",
            )
            self.assertIsNone(
                check_input_qualification(valid_input, "EQUITY", "INFY"),
                f"Expected '{valid_input}' not to be intercepted as gibberish",
            )

        for invalid_mash in ["12345678", "123456789", "1111111", "asdfghjkl", "zzzzzzzz"]:
            self.assertFalse(
                is_input_qualified(invalid_mash),
                f"Expected '{invalid_mash}' to be rejected as gibberish",
            )

    def test_multi_turn_parameterized_calculator_and_sticky_section_escape(self):
        """Verifies multi-turn numeric simulations ('10000', '15%', '15y'), sticky section override, and passage retrieval."""
        sample_report = {
            "report_text": (
                "### Pillar 01: Historical Scars & Management Governance\n"
                "Management has maintained zero promoter share pledging.\n\n"
                "### Pillar 03: Balance Sheet & Cash Flow Forensics\n"
                "Working capital cycle improved by 14 days as receivable days (DSO) tightened from 68 to 54 days and inventory turnover accelerated.\n\n"
                "### Pillar 05: Valuation & Reverse DCF\n"
                "Current market price implies 11.2% annual FCF compounding over 10 years.\n"
            ),
            "baseline_price": 1500.0,
            "baseline_pe": 24.0,
            "baseline_mcap": 6200000000000,
            "short_name": "Infosys Ltd",
            "citations": [{"title": "Filing"}],
        }
        sample_fund = {"current_price": 1500.0, "pe_ratio": 24.0, "promoter_pledge_pct": 0.0}

        async def _run():
            with patch("core.db.reports.get_report_by_ticker_sync", return_value=sample_report), \
                 patch("core.db.fundamentals.get_cached_fundamentals", return_value=sample_fund):
                conv_id = "TEST-WS3-INTERACTIVE-FLOW"

                # Turn 1: User clicks Reverse DCF quick chip (sets section='reverse_dcf')
                t1 = await process_research_desk_turn(
                    conversation_id=conv_id,
                    user_message="What implied growth rate is priced into current CMP based on Reverse DCF?",
                    ticker="INFY",
                    asset_type="equity",
                    section="reverse_dcf",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Reverse DCF Valuation & Implied Growth Deconstruction", t1["response"])

                # Turn 2: User replies with single number "10000" (section='reverse_dcf' remains sticky)
                t2 = await process_research_desk_turn(
                    conversation_id=conv_id,
                    user_message="10000",
                    ticker="INFY",
                    asset_type="equity",
                    section="reverse_dcf",
                    deep_dive_unlocked=True,
                )
                self.assertNotEqual(t2.get("status"), "INPUT_UNQUALIFIED")
                self.assertIn("Live Parameterized Reverse-DCF & Allocation Simulation", t2["response"])
                self.assertIn("₹10,000", t2["response"])

                # Turn 3: User replies with "15%" — carries forward ₹10,000 from Turn 2 and re-computes at 15.0% CAGR
                t3 = await process_research_desk_turn(
                    conversation_id=conv_id,
                    user_message="15%",
                    ticker="INFY",
                    asset_type="equity",
                    section="reverse_dcf",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Live Parameterized Reverse-DCF & Allocation Simulation", t3["response"])
                self.assertIn("₹10,000", t3["response"])
                self.assertIn("15.0%", t3["response"])

                # Turn 4: Sticky section ('countercase') does NOT hijack an explicit question about working capital / receivables
                t4 = await process_research_desk_turn(
                    conversation_id=conv_id,
                    user_message="How are receivable days and inventory turnover trending?",
                    ticker="INFY",
                    asset_type="equity",
                    section="countercase",
                    deep_dive_unlocked=True,
                )
                self.assertNotIn("Countercase Analysis", t4["response"])
                self.assertIn("receivable days (DSO) tightened from 68 to 54 days", t4["response"])

                # Turn 5: Mutual Fund single-number follow-up ("10000") computes live Direct vs Regular fee drag
                mf_t1 = await process_research_desk_turn(
                    conversation_id="TEST-WS3-MF-FLOW",
                    user_message="10000",
                    ticker="122639",
                    asset_type="mutual_fund",
                    section="fee_drag",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Live Parameterized Fee-Drag & Compounding Simulation", mf_t1["response"])
                self.assertIn("₹10,000", mf_t1["response"])

                # Turn 6: Mutual Fund sticky section ('fee_drag') does NOT trap a question about Active Share
                mf_t2 = await process_research_desk_turn(
                    conversation_id="TEST-WS3-MF-FLOW",
                    user_message="Audit the active share and check for closet indexing",
                    ticker="122639",
                    asset_type="mutual_fund",
                    section="fee_drag",
                    deep_dive_unlocked=True,
                )
                self.assertIn("Active Share & Closet Indexing Diagnostic", mf_t2["response"])
                self.assertNotIn("Intermediary Fee Drag & Compounding Cost Audit", mf_t2["response"])

        asyncio.run(_run())

    def test_debt_covenant_and_guarantee_questions_not_deflected_as_advisory(self):
        """WS1.1 (#4): Verifies legitimate debt covenant and parent-guarantee questions containing 'guaranteed' are never deflected as SEBI retail advisory."""
        from core.agents.copilot.research_desk import (
            build_equity_deterministic_response,
            build_debt_deterministic_response,
        )
        legitimate_queries = [
            "Is the subsidiary debt guaranteed by the parent company?",
            "Are these NCDs guaranteed by state government or backed by DSCR covenants?",
            "What are the corporate guarantees and contingent liabilities on the balance sheet?",
            "Are the lease rentals guaranteed under the lock-in covenant?",
            "What was the statutory auditor's recommendation on internal controls?",
        ]
        for q in legitimate_queries:
            self.assertFalse(
                detect_forbidden_intent(q),
                f"Legitimate covenant/guarantee query falsely flagged as forbidden advisory: {q}"
            )

        # Genuine retail advisory 'guaranteed return' queries MUST still be intercepted
        self.assertTrue(detect_forbidden_intent("Can you give me a guaranteed return stock tip?"))
        self.assertTrue(detect_forbidden_intent("Which stock has guaranteed profits?"))

        # Equity deterministic builder must route 'debt guaranteed by parent' to Solvency, not SEBI advisory deflection
        eq_resp = build_equity_deterministic_response(
            context_data={"company_name": "Infosys Ltd", "baseline_price": 1520.0, "baseline_pe": 24.5},
            section=None,
            ticker="INFY",
            user_message="Is the subsidiary debt guaranteed by the parent company or backed by balance sheet covenants?",
        )
        self.assertNotIn("SEBI Regulatory Non-Advisory Notice", eq_resp)
        self.assertIn("Balance Sheet Solvency & Liquidity Diagnostic", eq_resp)

        # Debt deterministic builder must route 'guaranteed by DSCR covenants' to Covenant Headroom
        debt_resp = build_debt_deterministic_response(
            context_data={"instrument_name": "7.85% HDFC Bank AAA NCD", "credit_rating": "CRISIL AAA", "seniority_tier": "SENIOR_SECURED"},
            section=None,
            ticker="INE040A08351",
            user_message="Are these bonds guaranteed by collateral covenants and what is the DSCR headroom?",
        )
        self.assertNotIn("SEBI Regulatory Non-Advisory Notice", debt_resp)
        self.assertIn("Asset Coverage & Covenant Headroom", debt_resp)

    def test_copilot_turn_with_dynamic_entity_override(self):
        """Verifies end-to-end Copilot turn switches entity seamlessly mid-conversation."""
        async def _run():
            res = await process_research_desk_turn(
                conversation_id="TEST-COPILOT-DYNAMIC-OVERRIDE",
                user_message="What about INFY? What is its PE multiple?",
                ticker="TCS",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("INFY", resp)
            self.assertIn("Valuation & Multiples Diagnostic", resp)
            self.assertIn("Free Tier", resp)

        asyncio.run(_run())

    def test_llm_route_generative_synthesis_when_entitled(self):
        """Verifies that entitled users on main successfully route through Gemini LLM synthesis."""
        async def _run():
            from unittest.mock import patch, MagicMock, AsyncMock
            import core.agents.copilot.research_desk as fd
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = "Here is the forensic analysis compiled by Gemini."
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

            with patch.dict(os.environ, {"TESTING": "0", "PYTEST_CURRENT_TEST": ""}), \
                 patch.object(fd, "get_secret", return_value="fake_api_key"), \
                 patch("google.genai.Client", return_value=mock_client):
                res = await process_research_desk_turn(
                    conversation_id="TEST-LLM-SUCCESS",
                    user_message="What shocked you about this stock?",
                    ticker="INFY",
                    deep_dive_unlocked=True,
                    is_subscriber=True
                )
                self.assertEqual(res["status"], "COMPLETED")
                self.assertIn("Generative Synthesis (Unlocked Deep Dive / Pro Tier)", res["response"])
                self.assertIn("Here is the forensic analysis", res["response"])
                mock_client.aio.models.generate_content.assert_called_once()

        asyncio.run(_run())

    def test_reit_copilot_chat_turn(self):
        """Verifies REIT asset class grounding, Section 115UA waterfall, and NDCF purity response."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-COPILOT-101",
            "message": "Evaluate the Section 115UA tax waterfall and NDCF payout purity for this trust.",
            "ticker": "EMBASSY",
            "asset_type": "reit"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        response_text = data.get("response", "")
        self.assertIn("Section 115UA Tax Distribution Waterfall", response_text)
        self.assertIn("Post-Tax Yield at 30% Marginal Slab", response_text)
        self.assertIn("Return of Capital / Amortization", response_text)

    def test_reit_post_tax_yield_slabs_table(self):
        """Verifies multi-slab yield simulation table with 0%, 10%, 20%, 30%, 39% slabs."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-SLABS-102",
            "message": "Break down the post-tax yield across the 0%, 10%, 20%, 30%, and 39% tax slabs for this REIT/InvIT.",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "tax_waterfall"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Multi-Slab Post-Tax Yield Simulation", text)
        self.assertIn("Marginal Tax Slab", text)
        self.assertIn("39% (Peak HNI)", text)
        self.assertIn("Tax Shield Efficiency", text)

    def test_reit_roc_tax_treatment(self):
        """Verifies Return of Capital & Section 56(2)(xii) analysis."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-ROC-103",
            "message": "Explain the tax treatment of Return of Capital (Amortization) and Section 56(2)(xii) specified sum threshold.",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "tax_waterfall"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Section 56(2)(xii)", text)
        self.assertIn("Specified Sum", text)
        self.assertIn("Cost Base Reduction", text)

    def test_reit_spv_dividend_exemption(self):
        """Verifies SPV Dividend Section 10(23FD) vs Section 115BAA corporate tax analysis."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-DIV-104",
            "message": "Is the dividend component exempt or taxable in unitholder hands based on SPV Sec 115BAA status?",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "tax_waterfall"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("SPV Dividend Tax Pass-Through Audit", text)
        self.assertIn("Section 10(23FD)", text)
        self.assertIn("Section 115BAA", text)

    def test_reit_sebi_15pct_penal_clause(self):
        """Verifies SEBI 15% p.a. penal interest enforcement clause response."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-PENAL-105",
            "message": "Does this trust risk the SEBI 15% penal interest rate for delayed distributions?",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "ndcf_purity"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("SEBI 15% p.a. Penal Interest Enforcement Audit", text)
        self.assertIn("15 working days", text)
        self.assertIn("Investment Manager", text)

    def test_reit_fcf_vs_ndcf(self):
        """Verifies spread analysis between true Operating FCF and Accounting NDCF."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-FCF-106",
            "message": "Analyze the spread between accounting Net Distributable Cash Flow and true operating free cash flow.",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "ndcf_purity"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Operating Free Cash Flow (FCF)", text)
        self.assertIn("Maintenance Capex Deductions", text)

    def test_reit_lease_expiry_and_renewals(self):
        """Verifies Lease Expiry schedule, WALE, and contractual escalations response."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-LEASE-107",
            "message": "Analyze the lease expiry concentration and renewal risk over the next 3 years.",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "portfolio_wale"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Lease Expiry Schedule & Re-Leasing Pipeline", text)
        self.assertIn("Contractual Rental Escalations", text)

    def test_reit_top_tenant_concentration(self):
        """Verifies Top 3 anchor tenant concentration and GCC counterparty response."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-TENANT-108",
            "message": "How vulnerable is distribution cash flow if the top 3 tenants vacate or downsize?",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "portfolio_wale"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Anchor Tenant Quality & Counterparty Concentration", text)
        self.assertIn("Downside Protection", text)

    def test_reit_rate_hike_shock(self):
        """Verifies +150 bps interest rate and cap-rate expansion stress test."""
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": "TEST-REIT-RATE-109",
            "message": "How does a 150 bps rise in benchmark bond yields impact the unit price and NAV cap rate?",
            "ticker": "PROPSHARE",
            "asset_type": "reit",
            "section": "inversion"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        text = data.get("response", "")
        self.assertIn("Sensitivity Stress-Test", text)
        self.assertIn("+150 bps Benchmark Yield Spike", text)




"""
tests/test_admin_copilot.py
==============================================================================
Unit & Integration Tests for Admin Executive Copilot and Two-Step Action Engine.
==============================================================================
"""

import os
import unittest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from web.main import app
from web.common import _generate_admin_token, ADMIN_COOKIE_NAME
from core.db import init_db
from core.db.admin import get_admin_user, add_admin_user
from core.db.users import get_or_create_user
from core.db.support import create_support_ticket, get_support_tickets
from core.agents.copilot.admin_copilot import (
    AdminActionType,
    tool_get_admin_dashboard_kpis,
    tool_get_billables_summary,
    tool_get_support_tickets_summary,
    tool_lookup_user_account,
    tool_get_admin_audit_trail,
    create_action_proposal,
    execute_confirmed_admin_action,
    process_admin_copilot_turn,
)


class TestAdminCopilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        init_db()

        cls.owner_email = "lyndnpnto@gmail.com"
        cls.owner_token = _generate_admin_token(cls.owner_email, "owner")

        cls.viewer_email = "test_viewer@moatnomics.internal"
        add_admin_user(cls.viewer_email, role="viewer")
        cls.viewer_token = _generate_admin_token(cls.viewer_email, "viewer")

        cls.test_user_email = "copilot_user@example.com"
        get_or_create_user(user_id="usr_copilot_test_1", email=cls.test_user_email, full_name="Copilot User")

    def setUp(self):
        self.client = TestClient(app)
        get_or_create_user(user_id="usr_copilot_test_1", email=self.test_user_email, full_name="Copilot User")

    def test_analytical_tools_execution(self):
        """Verify data tools retrieve live metrics cleanly without exceptions."""
        kpis = tool_get_admin_dashboard_kpis(window="30d", exclude_tests=False)
        self.assertIsInstance(kpis, dict)
        self.assertIn("unique_sessions", kpis)
        self.assertIn("gross_revenue_inr", kpis)
        self.assertIn("net_revenue_inr", kpis)
        self.assertIn("open_tickets_count", kpis)

        billables = tool_get_billables_summary(window="30d", limit=5)
        self.assertIsInstance(billables, dict)
        self.assertIn("recent_transactions", billables)

        tickets = tool_get_support_tickets_summary(status="all", limit=5, exclude_tests=False)
        self.assertIsInstance(tickets, list)

        user_info = tool_lookup_user_account(self.test_user_email)
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info["email"], self.test_user_email)
        self.assertIn("credits_balance", user_info)

        audit_trail = tool_get_admin_audit_trail(limit=5)
        self.assertIsInstance(audit_trail, list)

    def test_create_action_proposal(self):
        """Verify proposal payload structure and strict two-step confirmation requirement."""
        prop = create_action_proposal(
            action_type=AdminActionType.GRANT_CREDITS,
            title="Grant 5.0 Credits",
            summary="Allocate credits to test user.",
            payload={"target_user": self.test_user_email, "credits": 5.0},
            impact_level="MEDIUM",
            impact_warning="Credits balance will increase."
        )
        self.assertTrue(prop["requires_confirmation"])
        self.assertEqual(prop["action_type"], AdminActionType.GRANT_CREDITS)
        self.assertEqual(prop["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(prop["payload"]["credits"], 5.0)

    def test_execute_confirmed_admin_action_rbac_and_grant_credits(self):
        """Verify role-based access control and state mutation for credit grant."""
        # Viewer attempt -> must be rejected
        viewer_user = {"email": self.viewer_email, "role": "viewer"}
        res_viewer = execute_confirmed_admin_action(
            action_type=AdminActionType.GRANT_CREDITS,
            payload={"target_user": self.test_user_email, "credits": 3.0},
            admin_user=viewer_user
        )
        self.assertFalse(res_viewer["success"])
        self.assertIn("Forbidden", res_viewer["error"])

        # Owner attempt -> must succeed
        owner_user = {"email": self.owner_email, "role": "owner"}
        res_owner = execute_confirmed_admin_action(
            action_type=AdminActionType.GRANT_CREDITS,
            payload={
                "target_user": self.test_user_email,
                "credits": 4.0,
                "reason": "TASK_REMEDY",
                "admin_note": "Copilot Unit Test Grant"
            },
            admin_user=owner_user
        )
        self.assertTrue(res_owner.get("success"), f"Grant failed: {res_owner}")
        self.assertEqual(res_owner.get("credits_added"), 4.0)

        # Verify new balance via tool
        user_info = tool_lookup_user_account(self.test_user_email)
        self.assertGreaterEqual(user_info["credits_balance"], 4.0)

    def test_execute_confirmed_admin_action_ticket_update(self):
        """Verify support grievance ticket status update via action engine."""
        tkt = create_support_ticket(
            user_email="copilot_tkt@example.com",
            subject="Test Inquiry for Copilot",
            message="Needs resolution"
        )
        ticket_id = tkt["ticket_id"]

        owner_user = {"email": self.owner_email, "role": "owner"}
        res_update = execute_confirmed_admin_action(
            action_type=AdminActionType.UPDATE_TICKET,
            payload={
                "ticket_id": ticket_id,
                "status": "resolved",
                "admin_notes": "Resolved via Copilot Action Execution"
            },
            admin_user=owner_user
        )
        self.assertTrue(res_update["success"])
        self.assertEqual(res_update["status"], "resolved")

        # Verify ticket in DB
        tickets = get_support_tickets(status="resolved", limit=10, exclude_tests=False)
        found = any(t["ticket_id"] == ticket_id for t in tickets)
        self.assertTrue(found)

    def test_execute_confirmed_admin_action_purge_test_data(self):
        """Verify purging test telemetry via action engine."""
        owner_user = {"email": self.owner_email, "role": "owner"}
        res_purge = execute_confirmed_admin_action(
            action_type=AdminActionType.PURGE_TEST_DATA,
            payload={},
            admin_user=owner_user
        )
        self.assertTrue(res_purge["success"])
        self.assertIn("counts", res_purge)

    def test_process_admin_copilot_turn_analytical_query(self):
        """Verify analytical Q&A queries return grounded data answers without proposals."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="What are our unique sessions and total actions this month?"
        ))
        self.assertIn("Executive Telemetry & Site Usage", res["reply"])
        self.assertIsNone(res["action_proposal"])
        self.assertIn("COMPLETED", res["status"])

    def test_process_admin_copilot_turn_grant_credits_intent(self):
        """Verify credit grant requests generate a structured action proposal."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message=f"Grant 5.0 credits to {self.test_user_email} for downtime remedy"
        ))
        self.assertIsNotNone(res["action_proposal"])
        prop = res["action_proposal"]
        self.assertEqual(prop["action_type"], AdminActionType.GRANT_CREDITS)
        self.assertEqual(prop["payload"]["target_user"], self.test_user_email)
        self.assertEqual(prop["payload"]["credits"], 5.0)
        self.assertTrue(prop["requires_confirmation"])

    def test_process_admin_copilot_turn_grant_credits_to_self(self):
        """Verify credit requests targeting 'myself' or 'me' automatically resolve to admin email and directly execute."""
        import asyncio
        from core.db.users import get_user_by_email
        owner_user = {"email": self.owner_email, "role": "owner"}

        # Fetch baseline balance (ensuring account initialized)
        from core.db.users import get_or_create_user
        u_before = get_user_by_email(self.owner_email)
        if not u_before:
            u_before = get_or_create_user(user_id="usr_owner_test", email=self.owner_email, full_name="Owner")
        base_bal = float(u_before.get("credits_balance", 0.0))

        # 1. "send some credits to myself" -> Auto-executes without confirmation friction
        res1 = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="send some credits to myself"
        ))
        self.assertIsNone(res1["action_proposal"])
        self.assertEqual(res1["status"], "COMPLETED_EXECUTED")
        self.assertIn("Successfully Granted 5.0 Research Credits", res1["reply"])
        self.assertEqual(res1["new_balance"], base_bal + 5.0)

        # Verify in database
        u_after1 = get_user_by_email(self.owner_email)
        self.assertEqual(float(u_after1["credits_balance"]), base_bal + 5.0)

        # 2. "give me 10 credits"
        res2 = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="give me 10 credits"
        ))
        self.assertIsNone(res2["action_proposal"])
        self.assertEqual(res2["status"], "COMPLETED_EXECUTED")
        self.assertIn("Successfully Granted 10.0 Research Credits", res2["reply"])
        self.assertEqual(res2["new_balance"], base_bal + 15.0)

        u_after2 = get_user_by_email(self.owner_email)
        self.assertEqual(float(u_after2["credits_balance"]), base_bal + 15.0)

    def test_api_admin_copilot_chat_endpoint_unauthorized(self):
        """Verify /api/admin/copilot/chat blocks unauthenticated access with 403."""
        res = self.client.post(
            "/api/admin/copilot/chat",
            json={"message": "How many sessions today?"}
        )
        self.assertEqual(res.status_code, 403)

    def test_api_admin_copilot_chat_endpoint_authenticated(self):
        """Verify /api/admin/copilot/chat responds 200 with reply for authenticated admin."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.owner_token)
        res = self.client.post(
            "/api/admin/copilot/chat",
            json={
                "message": "Summarize our net cash inflow and billables.",
                "context": {"window": "30d", "include_tests": 0}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("Cash Flow & Revenue Diagnostics", data.get("reply", ""))

    def test_api_admin_copilot_execute_endpoint(self):
        """Verify /api/admin/copilot/execute executes confirmed proposals."""
        self.client.cookies.set(ADMIN_COOKIE_NAME, self.owner_token)
        res = self.client.post(
            "/api/admin/copilot/execute",
            json={
                "action_type": AdminActionType.GRANT_CREDITS,
                "payload": {
                    "target_user": self.test_user_email,
                    "credits": 2.0,
                    "reason": "TASK_REMEDY",
                    "admin_note": "API execute endpoint test"
                },
                "proposal_id": "prop_test_123"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("credits_added"), 2.0)

    def test_admin_copilot_ticket_lookup_and_reply_proposal_and_execution(self):
        """Verify live ticket list, specific TKT-* inspection, multi-turn REPLY_TICKET proposal, and confirmed execution."""
        import asyncio
        from core.db.support import create_support_ticket, get_ticket_by_id
        owner_user = {"email": self.owner_email, "role": "owner"}

        tkt = create_support_ticket(
            user_email="rahul.sharma@example.com",
            user_name="Rahul Sharma",
            category="billing",
            subject="Credits not reflected after checkout",
            message="Completed payment of Rs 499 but balance is still 0.",
        )
        tkt_id = tkt["ticket_id"]

        # 1. List open support tickets (including test domain tickets)
        res_list = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Show me open support tickets",
            context={"include_tests": 1},
        ))
        self.assertIn("Support Grievances & Complaints Docket", res_list["reply"])
        self.assertIn(tkt_id, res_list["reply"])

        # 2. Inspect specific ticket
        res_detail = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message=f"Inspect ticket {tkt_id}"
        ))
        self.assertIn(tkt_id, res_detail["reply"])
        self.assertIn("Completed payment of Rs 499", res_detail["reply"])

        # 3. Multi-turn follow-up: "Reply to it saying: We have credited your account with 5.0 credits."
        history = [
            {"role": "user", "content": f"Inspect ticket {tkt_id}"},
            {"role": "assistant", "content": res_detail["reply"]},
        ]
        res_reply_prop = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Reply to it saying: We have credited your account with 5.0 credits.",
            history=history,
        ))
        self.assertIsNotNone(res_reply_prop["action_proposal"])
        prop = res_reply_prop["action_proposal"]
        self.assertEqual(prop["action_type"], AdminActionType.REPLY_TICKET)
        self.assertEqual(prop["payload"]["ticket_id"], tkt_id)
        self.assertIn("We have credited your account with 5.0 credits.", prop["payload"]["reply_message"])
        self.assertTrue(prop["requires_confirmation"])

        # 4. Execute confirmed REPLY_TICKET proposal
        exec_payload = dict(prop["payload"], dispatch_email=False)
        exec_res = execute_confirmed_admin_action(
            admin_user=owner_user,
            action_type=prop["action_type"],
            payload=exec_payload,
        )
        self.assertTrue(exec_res["success"])
        self.assertEqual(exec_res["ticket_id"], tkt_id)
        updated_tkt = get_ticket_by_id(tkt_id, include_responses=True)
        self.assertEqual(updated_tkt["status"], "resolved")
        self.assertTrue(any("We have credited your account" in r.get("message", "") for r in updated_tkt.get("responses", [])))

    def test_admin_copilot_user_account_lookup_and_multiturn_credit_grant(self):
        """Verify live user account inspection and multi-turn entity carry-forward for credit grants."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        # 1. Look up user account
        res_lookup = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message=f"Look up user {self.test_user_email}"
        ))
        self.assertIn("Live User Account Profile", res_lookup["reply"])
        self.assertIn(self.test_user_email, res_lookup["reply"])

        # 2. Multi-turn follow-up without repeating email: "Grant 3 credits"
        history = [
            {"role": "user", "content": f"Look up user {self.test_user_email}"},
            {"role": "assistant", "content": res_lookup["reply"]},
        ]
        res_grant = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Grant 3 credits",
            history=history,
        ))
        self.assertIsNotNone(res_grant["action_proposal"])
        prop = res_grant["action_proposal"]
        self.assertEqual(prop["action_type"], AdminActionType.GRANT_CREDITS)
        self.assertEqual(prop["payload"]["target_user"], self.test_user_email)
        self.assertEqual(prop["payload"]["credits"], 3.0)

    def test_admin_copilot_provider_quotas_and_ai_spends_qa(self):
        """Verify subscribed provider quota & Gemini AI spend telemetry Q&A."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Show subscribed provider quotas and Gemini AI spends"
        ))
        self.assertIn("Subscribed Provider Quotas & AI Spend Monitoring", res["reply"])
        self.assertIn("Cumulative Gemini Token & Spend Ledger", res["reply"])
        self.assertIn("Google Gemini API", res["reply"])

    def test_admin_copilot_data_driven_optimization_tips_and_elliptical_followup(self):
        """Verify data-driven site metrics & performance optimization playbook and elliptical 'yes' follow-up."""
        import asyncio
        owner_user = {"email": self.owner_email, "role": "owner"}

        res_tips = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Give me data-driven tips and tricks to improve site metrics, conversion, and performance"
        ))
        self.assertIn("Data-Driven Site Metrics & Performance Optimization Playbook", res_tips["reply"])
        self.assertIn("1. **", res_tips["reply"])
        self.assertIn("2. **", res_tips["reply"])
        self.assertIn("3. **", res_tips["reply"])
        self.assertIn("4. **Expand Long-Tail Multi-Asset Discovery", res_tips["reply"])
        self.assertIn("5. **Service Desk SLA & Provider Quota Hygiene", res_tips["reply"])

        # Verify elliptical affirmation ("yes") after executive overview resolves to optimization tips
        res_overview = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="Give me an executive overview"
        ))
        history = [
            {"role": "user", "content": "Give me an executive overview"},
            {"role": "assistant", "content": res_overview["reply"]},
        ]
        res_followup = asyncio.run(process_admin_copilot_turn(
            admin_user=owner_user,
            message="yes",
            history=history,
        ))
        self.assertIn("Data-Driven Site Metrics & Performance Optimization Playbook", res_followup["reply"])

    def test_admin_copilot_trigger_project_audit_inside_async_event_loop(self):
        """Verify TRIGGER_PROJECT_AUDIT safely executes inside an active asyncio event loop without RuntimeError."""
        import asyncio
        from unittest.mock import patch
        import core.audit.project_auditor
        owner_user = {"email": self.owner_email, "role": "owner"}

        async def fake_audit_coro(use_ai=True):
            # Simulates async audit_project_full coroutine executed inside a running event loop
            await asyncio.sleep(0.001)
            return {"audit_id": "AUD-TEST-99", "overall_status": "PASS", "overall_score": 99.5}

        async def _invoke_from_running_loop():
            with patch.object(core.audit.project_auditor, "audit_project_full", side_effect=fake_audit_coro):
                return execute_confirmed_admin_action(
                    admin_user=owner_user,
                    action_type=AdminActionType.TRIGGER_PROJECT_AUDIT,
                    payload={"quick": True},
                )

        res = asyncio.run(_invoke_from_running_loop())
        self.assertTrue(res["success"])
        self.assertEqual(res["audit_id"], "AUD-TEST-99")
        self.assertEqual(res["score"], 99.5)




"""Comprehensive unit and integration test suite for Sitewide Google Antigravity Agents.

Verifies:
- Shared agent configurations, declarative policies, and budget limits
- Database dual-binding for agent conversations, turns, and event ledgers
- Domain research squads (Equities, Funds, Debt, REITs, Macro)
- Non-advisory regulatory compliance deflection
- Interactive Copilot API endpoints
"""

import os
import uuid
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from web.main import app
from core.agents.config import (
    ANTIGRAVITY_AVAILABLE,
    get_default_agent_policies,
    get_tier_budget_config,
    SEBI_SAFE_HARBOR_DIRECTIVE
)
from core.db.agent_sessions import (
    create_or_get_agent_conversation,
    append_conversation_turn,
    get_conversation_turns,
    record_autonomous_event,
    get_recent_autonomous_events
)
from core.agents.equity.forensic_squad import run_deterministic_equity_audit
from core.agents.funds.lookthrough_squad import audit_fund_lookthrough
from core.agents.debt.credit_squad import audit_credit_offering
from core.agents.reits.real_assets_squad import audit_real_asset, scan_sgb_parity_discounts
from core.agents.macro.macro_squad import audit_macro_yield_environment
from core.agents.copilot.research_desk import (
    check_non_advisory_compliance,
    process_research_desk_turn
)


class TestSitewideAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "1"
        os.environ["AUDIT_RECURSION_GUARD"] = "1"
        cls.client = TestClient(app)

    def test_agent_policies_and_budgets(self):
        """Verifies policy lists and operational tier budget limits."""
        policies = get_default_agent_policies()
        self.assertIsInstance(policies, list)

        budget_domain = get_tier_budget_config("domain_research")
        if ANTIGRAVITY_AVAILABLE:
            self.assertIsNotNone(budget_domain)
            self.assertEqual(budget_domain.max_model_calls, 15)
            budget_copilot = get_tier_budget_config("interactive_copilot")
            self.assertIsNotNone(budget_copilot)
            self.assertEqual(budget_copilot.max_model_calls, 8)
        else:
            self.assertIsNone(budget_domain)

    def test_agent_sessions_and_turns_crud(self):
        """Verifies persistence of agent conversations and dialogue turns."""
        conv_id = f"TEST-CONV-{uuid.uuid4().hex[:8]}"
        conv = create_or_get_agent_conversation(
            conversation_id=conv_id,
            user_id="usr_test_allocator",
            agent_type="equity_copilot",
            context_ticker="INFY"
        )
        self.assertEqual(conv.get("conversation_id"), conv_id)
        self.assertEqual(conv.get("context_ticker"), "INFY")

        appended = append_conversation_turn(conv_id, "user", "What is the margin of safety?")
        self.assertTrue(appended)
        appended_agent = append_conversation_turn(conv_id, "agent", "Estimated margin of safety is 38.5%.")
        self.assertTrue(appended_agent)

        turns = get_conversation_turns(conv_id)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["sender_role"], "user")
        self.assertEqual(turns[1]["sender_role"], "agent")

    def test_autonomous_event_ledger(self):
        """Verifies recording and querying of autonomous event ledger."""
        evt_id = record_autonomous_event(
            event_type="test_bse_filing",
            ticker="TCS",
            trigger_source="unit_test",
            action_taken="dispatched_audit",
            summary="Test autonomous event recording"
        )
        self.assertTrue(evt_id.startswith("EVT-"))

        events = get_recent_autonomous_events(limit=5, event_type="test_bse_filing", include_test_events=True)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["ticker"], "TCS")

        # Clean up test event so DB remains unpolluted
        from core.db.connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM autonomous_event_ledger WHERE event_id = ?", (evt_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    @patch("core.agents.tools_base.fetch_latest_bse_announcement", return_value="Board approved interim dividend and audited accounts.")
    def test_equity_forensic_squad(self, mock_bse):
        """Verifies equity squad deterministic output and non-advisory compliance."""
        audit = run_deterministic_equity_audit("INFY")
        self.assertEqual(audit["ticker"], "INFY")
        self.assertIn("composite_forensic_score", audit)
        self.assertIn("accounting_forensics", audit)
        self.assertIn("governance_scrutiny", audit)
        self.assertIn("valuation_stress", audit)
        self.assertIn("2(u)", audit["sebi_safe_harbor"])

    def test_fund_lookthrough_squad(self):
        """Verifies mutual fund look-through squad."""
        res = audit_fund_lookthrough("PPFAS_FLEXICAP_DIR")
        self.assertEqual(res["scheme_code"], "PPFAS_FLEXICAP_DIR")
        self.assertIn("has_sufficient_coverage", res)
        self.assertIn("weighted_moat_score", res)
        if res.get("has_sufficient_coverage"):
            self.assertGreater(res["composite_health_score"], 0.0)
        else:
            self.assertIsNone(res["composite_health_score"])

    def test_credit_and_real_assets_squads(self):
        """Verifies credit, REIT, and macro squads."""
        debt_res = audit_credit_offering("INE002A08012")
        self.assertIn("credit_score", debt_res)

        reit_res = audit_real_asset("EMBASSY")
        self.assertIn("compliance_score", reit_res)

        sgb_res = scan_sgb_parity_discounts()
        self.assertIn("total_tranches_scanned", sgb_res)

        macro_res = audit_macro_yield_environment()
        self.assertIn("benchmark_10y_gsec", macro_res)

    def test_non_advisory_compliance_filter(self):
        """Verifies regulatory deflection of retail buy/sell inquiries."""
        deflected = check_non_advisory_compliance("Should I buy INFY today?")
        self.assertIsNotNone(deflected)
        self.assertIn("SEBI Regulatory Non-Advisory Notice", deflected)
        self.assertIn("Section 2(u)", deflected)

        clean = check_non_advisory_compliance("Explain the ROCE trend over 3 years")
        self.assertIsNone(clean)

    def test_detect_forbidden_intent_word_boundary_isolation(self):
        """Verifies word boundaries prevent false positives on words like 'multiple', 'stipend', 'typical'."""
        false_positive_candidates = [
            "explain the PE multiple",
            "what is the typical debt to equity ratio?",
            "stipend expenses in employee costs",
            "participating preference shares"
        ]
        for query in false_positive_candidates:
            self.assertFalse(detect_forbidden_intent(query), f"'{query}' should NOT trigger forbidden intent.")
            self.assertIsNone(check_non_advisory_compliance(query))

        true_positives = [
            "stop loss for reliance",
            "give me a guaranteed return",
            "what is a sure shot stock?",
            "today intraday pick",
            "tomorrow target price",
            "which stock to buy",
            "best fund to buy",
            "should i invest in hdfc",
            "is it a good buy"
        ]
        for query in true_positives:
            self.assertTrue(detect_forbidden_intent(query), f"'{query}' MUST trigger forbidden intent.")
            self.assertIsNotNone(check_non_advisory_compliance(query))

    def test_copilot_turn_and_api(self):
        """Verifies Copilot chat processing and REST endpoints."""
        conv_id = f"TEST-API-COPILOT-{uuid.uuid4().hex[:8]}"
        # 1. Deflection turn via API
        resp = self.client.post("/api/copilot/chat", json={
            "conversation_id": conv_id,
            "message": "Is this stock a strong buy?",
            "ticker": "INFY"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "REGULATORY_DEFLECTED")
        self.assertIn("Section 2(u)", data.get("response"))

        # 2. History endpoint
        resp_hist = self.client.get(f"/api/copilot/history?conversation_id={conv_id}")
        self.assertEqual(resp_hist.status_code, 200)
        hist_data = resp_hist.json()
        self.assertTrue(hist_data.get("success"))
        self.assertGreaterEqual(len(hist_data.get("turns")), 2)

        # 3. Mutual Fund section-aware turn via API
        conv_mf_id = f"TEST-API-COPILOT-MF-{uuid.uuid4().hex[:8]}"
        resp_mf = self.client.post("/api/copilot/chat", json={
            "conversation_id": conv_mf_id,
            "message": "Explain the distributor commission fee drag.",
            "ticker": "PPFAS_FLEXICAP_DIR",
            "asset_type": "mutual_fund",
            "section": "fee_drag",
            "section_label": "Intermediary Fee Drag"
        })
        self.assertEqual(resp_mf.status_code, 200)
        data_mf = resp_mf.json()
        self.assertTrue(data_mf.get("success"))
        self.assertIn("Fee Drag", data_mf.get("response"))
        self.assertNotIn("company's Margin of Safety", data_mf.get("response"))




"""
tests/test_zero_hallucination_and_grounding.py
==============================================================================
Source-Grounded & Anti-Fabrication Test Suite.
Enforces that templates, legal content, codebases, and public UI strings
strictly adhere to verified project facts established in user directives:

1. Zero Corporate Entity Hallucinations (No claims of registered operating entity).
2. Zero Tax/Service Code Hallucinations (No claims of SAC 998314 or fake GST classifications).
3. Zero Physical Office Address Hallucinations (No Indiranagar / 100 Feet Road / 560038).
4. Zero Public Email / Mailto Hallucinations (No support@stockresearch.app, grievance@..., etc.).
5. Zero Phone Number / Hotline Hallucinations (No fake +91 numbers or WhatsApp desks).
6. Author Name Placeholder Hygiene (No 'Lyndon Pinto' in UI placeholders or form examples).
7. Pure On-Site Feedback Mandate (Inquiries & complaints strictly routed via /contact).
8. SEBI Safe-Harbor Affirmation (Explicit disclaimer that platform is NOT registered under SEBI).
==============================================================================
"""

import os
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
LEGAL_FILE = PROJECT_ROOT / "web" / "legal_content.py"
CORE_DIR = PROJECT_ROOT / "core"


class TestZeroHallucinationAndGrounding(unittest.TestCase):
    """Regression test suite enforcing zero hallucination of contact, entity, or address details."""

    def setUp(self):
        self.template_files = []
        for root, _, files in os.walk(TEMPLATES_DIR):
            for f in files:
                if f.endswith((".html", ".jinja2")):
                    self.template_files.append(Path(root) / f)

        self.assertTrue(len(self.template_files) > 0, "Expected web templates to be found for scanning.")
        self.assertTrue(LEGAL_FILE.exists(), "Expected web/legal_content.py to exist.")

    def test_no_hallucinated_physical_addresses(self):
        """Ensures no hallucinated physical office locations (Indiranagar, 100 Feet Road, 560038) exist."""
        forbidden_address_patterns = [
            r"Indiranagar",
            r"100\s*Feet\s*Road",
            r"560038",
            r"Operational\s*Office:",
            r"Operational\s*Address:"
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_address_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated physical office address details in codebase:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_corporate_service_codes(self):
        """Ensures no hallucinated GST SAC codes (998314) exist in public templates or legal policies."""
        forbidden_sac_patterns = [
            r"SAC\s*(?:Code)?[:\s]*998314",
            r"\b998314\b",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_sac_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated SAC / GST service codes in public templates or legal policies:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_registered_operating_entity_claims(self):
        """Ensures the app does not imply or claim to be a registered corporate operating entity."""
        forbidden_entity_patterns = [
            r"Registered\s+Operating\s+Entity",
            r"Entity\s*Name:\s*Stock\s*Research\s*App",
            r"Entity:\s*Stock\s*Research\s*App\s*/\s*Equity\s*Research\s*AI",
            r"Corporate\s*Entity:",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_entity_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated corporate entity declarations in public files:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_public_support_emails(self):
        """Ensures no ungrounded public support emails or mailto links exist on the site."""
        forbidden_email_patterns = [
            r"support@stockresearch\.app",
            r"grievance@stockresearch\.app",
            r"privacy@stockresearch\.app",
            r"support@stockresearch\.ai",
            r"support@vestnomics\.app",
            r"grievance@vestnomics\.app",
            r"privacy@vestnomics\.app",
            r"support@vestnomics\.ai",
            r"support@moatnomics\.com",
            r"grievance@moatnomics\.com",
            r"privacy@moatnomics\.com",
            r"support@moatnomics\.ai",
            r"mailto:",
        ]

        # Scan all templates and legal files. Exclude admin.html which contains the whitelisted root owner email.
        scanned = [f for f in self.template_files if f.name != "admin.html"] + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_email_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated public email addresses or mailto links on the site:\n" + "\n".join(violations)
        )

    def test_no_hallucinated_phone_numbers(self):
        """Ensures no fake phone numbers, customer support hotlines, or WhatsApp desks are listed."""
        forbidden_phone_patterns = [
            r"\+91\s*98450",
            r"Support\s*Hotline",
            r"WhatsApp:\s*\+91",
            r"Direct\s*Phone:",
        ]

        scanned = self.template_files + [LEGAL_FILE]
        violations = []

        for fpath in scanned:
            content = fpath.read_text(encoding="utf-8")
            for pat in forbidden_phone_patterns:
                matches = re.findall(pat, content, re.IGNORECASE)
                if matches:
                    violations.append(f"{fpath.name} matched pattern '{pat}' ({len(matches)} occurrence(s))")

        self.assertEqual(
            violations, [],
            f"Found hallucinated phone numbers or hotline descriptions:\n" + "\n".join(violations)
        )

    def test_personal_name_placeholder_hygiene(self):
        """Ensures the author's personal name ('Lyndon Pinto') is NEVER featured in UI placeholders or examples."""
        # Check all public templates (excluding internal admin auth login which validates the root owner account)
        public_templates = [f for f in self.template_files if f.name != "admin.html"]
        violations = []

        for fpath in public_templates:
            content = fpath.read_text(encoding="utf-8")
            # Look for Lyndon Pinto as placeholder or example text
            if re.search(r"placeholder=[\"'].*Lyndon.*[\"']", content, re.IGNORECASE) or \
               re.search(r"e\.g\.,?\s*Lyndon", content, re.IGNORECASE):
                violations.append(f"{fpath.name} features 'Lyndon' in a placeholder or form example.")

        self.assertEqual(
            violations, [],
            f"Personal name hygiene violation found in UI templates:\n" + "\n".join(violations)
        )

    def test_sebi_safe_harbor_not_registered_affirmation(self):
        """Validates that statutory disclaimers explicitly affirm the platform is NOT registered under SEBI."""
        from core.db.compliance import MANDATORY_SEBI_DISCLAIMER
        from web.legal_content import POLICIES

        # Must explicitly affirm non-registration
        self.assertIn(
            "NOT registered as a Research Analyst or Investment Adviser",
            MANDATORY_SEBI_DISCLAIMER,
            "Mandatory SEBI disclaimer must explicitly state that the platform is not registered."
        )

        terms_content = POLICIES.get("terms", {}).get("content_html", "")
        self.assertIn(
            "Neither the Platform nor its operators are registered as Research Analysts",
            terms_content,
            "Terms of Service must clearly disclaim SEBI Research Analyst registration."
        )

    def test_contact_form_routes_to_on_site_management_console(self):
        """Ensures contact page and legal policies guide users strictly to the on-site form (/contact)."""
        contact_tmpl = TEMPLATES_DIR / "contact.html"
        self.assertTrue(contact_tmpl.exists())
        contact_text = contact_tmpl.read_text(encoding="utf-8")

        # Form must submit to /contact
        self.assertIn('action="/contact"', contact_text)
        self.assertIn('method="POST"', contact_text)

        # Must describe review by administration console
        self.assertIn("Admin Desk Review", contact_text)

    def test_no_antigravity_mentions_on_site(self):
        """Ensures zero mention of Google Antigravity or Antigravity exists in any user-facing template or static UI."""
        violations = []
        for fpath in self.template_files:
            content = fpath.read_text(encoding="utf-8")
            if re.search(r"antigravity", content, re.IGNORECASE):
                violations.append(f"{fpath.name} contains mention of 'Antigravity'")

        static_js_dir = PROJECT_ROOT / "web" / "static" / "js"
        if static_js_dir.exists():
            for fpath in static_js_dir.glob("*.js"):
                content = fpath.read_text(encoding="utf-8")
                if re.search(r"antigravity", content, re.IGNORECASE):
                    violations.append(f"{fpath.name} contains mention of 'Antigravity'")

        self.assertEqual(
            violations, [],
            f"Found forbidden 'Antigravity' mentions on site UI:\n" + "\n".join(violations)
        )




if __name__ == "__main__":
    unittest.main()

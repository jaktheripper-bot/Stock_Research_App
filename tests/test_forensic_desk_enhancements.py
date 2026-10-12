"""Unit tests for Forensic Desk Input Qualification, Open-Ended Synthesis, and Tier Gating."""

import os
import unittest
import asyncio
from fastapi.testclient import TestClient

from web.main import app, init_db
from core.agents.copilot.forensic_desk import (
    check_input_qualification,
    process_forensic_desk_turn
)


class TestForensicDeskEnhancements(unittest.TestCase):
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
            self.assertIn("What shocked you", intercept["response"])

    def test_input_qualification_greetings(self):
        """Verifies that casual greetings receive friendly onboarding orientation."""
        greeting_samples = ["hi", "hello", "hey", "good morning", "ping"]
        for sample in greeting_samples:
            intercept = check_input_qualification(sample, asset_class="EQUITY", ticker="INFY")
            self.assertIsNotNone(intercept, f"Expected '{sample}' to be intercepted as greeting.")
            self.assertEqual(intercept["status"], "GREETING")
            self.assertIn("Welcome to the Forensic Intelligence Desk", intercept["response"])

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

    def test_equity_open_ended_what_shocked_you(self):
        """Verifies that 'what shocked you?' yields real contextual anomalies, not a canned menu."""
        async def _run():
            res = await process_forensic_desk_turn(
                conversation_id="TEST-OPEN-ENDED-SHOCK",
                user_message="What shocked you during the research on this stock?",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Key Forensic Surprises & Structural Red Flags", resp)
            self.assertNotIn("Select a forensic diagnostic pillar to drill into:", resp)
            # Free tier distinction notice must be present
            self.assertIn("Free Tier", resp)

        asyncio.run(_run())

    def test_equity_open_ended_bear_thesis(self):
        """Verifies that 'summarize the bear thesis' yields structured downside vectors."""
        async def _run():
            res = await process_forensic_desk_turn(
                conversation_id="TEST-OPEN-ENDED-BEAR",
                user_message="Summarize the bear thesis for this stock.",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Institutional Bear Thesis Summary", resp)
            self.assertIn("Multiple De-Rating", resp)
            self.assertIn("Free Tier", resp)

        asyncio.run(_run())

    def test_equity_open_ended_bull_thesis(self):
        """Verifies that 'summarize the bull thesis' yields structural compounding vectors."""
        async def _run():
            res = await process_forensic_desk_turn(
                conversation_id="TEST-OPEN-ENDED-BULL",
                user_message="Summarize the bull thesis and upside catalysts.",
                ticker="INFY",
                asset_type="equity",
                deep_dive_unlocked=False
            )
            self.assertEqual(res["status"], "DETERMINISTIC_FALLBACK")
            resp = res["response"]
            self.assertIn("Institutional Bull Thesis Summary", resp)
            self.assertIn("Competitive Moat", resp)
            self.assertIn("Free Tier", resp)

    def test_tier_distinction_notice_unlocked_vs_free(self):
        """Verifies that unlocked / pro users receive verified Pro notice while free users get Free Tier notice."""
        async def _run():
            # Free user
            res_free = await process_forensic_desk_turn(
                conversation_id="TEST-TIER-FREE",
                user_message="Explain the balance sheet solvency.",
                ticker="INFY",
                deep_dive_unlocked=False,
                is_subscriber=False
            )
            self.assertIn("Free Tier", res_free["response"])

            # Unlocked report user
            res_unlocked = await process_forensic_desk_turn(
                conversation_id="TEST-TIER-UNLOCKED",
                user_message="Explain the balance sheet solvency.",
                ticker="INFY",
                deep_dive_unlocked=True,
                is_subscriber=False
            )
            self.assertIn("Your entitlement is verified (Unlocked/Pro)", res_unlocked["response"])

            # Subscriber user
            res_sub = await process_forensic_desk_turn(
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
            res = await process_forensic_desk_turn(
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
            res = await process_forensic_desk_turn(
                conversation_id="TEST-DEBT-SHOCK",
                user_message="What shocked you or stood out in this bond?",
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
        self.assertIn("Welcome to the Forensic Intelligence Desk", data.get("response"))


if __name__ == "__main__":
    unittest.main()

"""PDF export must honour the Pillar 03/05 paywall and stamp a personal-use watermark."""
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from core.reporting.pdf import apply_pdf_watermark

REPORT = (
    "## Pillar 1: Macro\nMacro text\n\n"
    "## Pillar 3: Cash Flow Solvency\nSECRET_P3 coverage detail\n\n"
    "## Pillar 5: Valuation\nSECRET_P5 intrinsic value\n\n"
    "## Pillar 6: Technical\nTechnical text\n"
)


def _tiny_pdf() -> bytes:
    try:
        import pymupdf as fitz_mod
    except ImportError:
        import fitz as fitz_mod
    doc = fitz_mod.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Body text")
    data = doc.tobytes()
    doc.close()
    return data


def _text_of(pdf: bytes) -> str:
    try:
        import pymupdf as fitz_mod
    except ImportError:
        import fitz as fitz_mod
    doc = fitz_mod.open(stream=pdf, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    doc.close()
    return text


class TestWatermark(unittest.TestCase):
    def test_stamps_notice_and_account_ref(self):
        out = _text_of(apply_pdf_watermark(_tiny_pdf(), "usr_abc123"))
        self.assertIn("Body text", out)
        self.assertIn("Personal, non-commercial use only", out)
        self.assertIn("usr_abc123", out)

    def test_anonymous_has_notice_without_account(self):
        out = _text_of(apply_pdf_watermark(_tiny_pdf(), ""))
        self.assertIn("Redistribution is prohibited", out)
        self.assertNotIn("Licensed to account", out)

    def test_fails_open_on_bad_input(self):
        self.assertEqual(apply_pdf_watermark(b"not a pdf", "x"), b"not a pdf")


class TestPdfPaywall(unittest.TestCase):
    def _download(self, headers=None):
        from web.main import app
        captured = {}

        def fake_generate(ticker, rep_text, **kwargs):
            captured["text"] = rep_text
            return _tiny_pdf()

        rep = {"report_text": REPORT, "citations": []}
        with mock.patch.dict(os.environ, {"TESTING": "1"}), \
             mock.patch("web.main.get_report_by_ticker_sync", return_value=rep), \
             mock.patch("web.main.get_historical_prices", return_value=None), \
             mock.patch("core.reporting.pdf.generate_report_pdf", side_effect=fake_generate):
            resp = TestClient(app).get("/api/pdf/INFY", headers=headers or {})
        return resp, captured.get("text", "")

    def test_locked_user_pdf_excludes_gated_pillars(self):
        resp, text = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("SECRET_P3", text)
        self.assertNotIn("SECRET_P5", text)
        self.assertIn("Macro text", text)
        self.assertIn("Unlock this ticker", text)

    def test_unlocked_user_pdf_has_full_report(self):
        resp, text = self._download({"x-unlock-preview": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("SECRET_P3", text)
        self.assertIn("SECRET_P5", text)

    def test_pdf_response_is_watermarked(self):
        resp, _ = self._download()
        self.assertIn("Personal, non-commercial use only", _text_of(resp.content))


if __name__ == "__main__":
    unittest.main()

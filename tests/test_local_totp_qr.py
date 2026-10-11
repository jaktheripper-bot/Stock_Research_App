"""Guards the admin 2FA QR code against leaking the TOTP secret to third parties."""
import base64
import re
import unittest
from pathlib import Path

from web.main import _build_local_qr_data_uri

ROOT = Path(__file__).resolve().parent.parent


class TestLocalTotpQr(unittest.TestCase):
    def test_qr_is_inline_svg_data_uri(self):
        uri = _build_local_qr_data_uri("otpauth://totp/Test:a@b.com?secret=ABC&issuer=Test")
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        self.assertIn("<svg", svg)

    def test_no_third_party_qr_service_in_source(self):
        src = (ROOT / "web" / "main.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"qrserver\.com|chart\.googleapis\.com/chart\?cht=qr", src))


if __name__ == "__main__":
    unittest.main()

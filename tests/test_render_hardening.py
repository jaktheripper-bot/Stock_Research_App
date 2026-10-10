"""Unit tests for Render Production Hardening & Boot Guards.

Verifies:
1. render.yaml declares SECRET_KEY, ADMIN_API_KEY, ADMIN_PASSWORD with sync: false.
2. render.yaml startCommand configures --workers 2.
3. Production boot guard rejects missing, short, or fallback SECRET_KEY when ENVIRONMENT=production or RENDER=true.
4. Production boot guard accepts valid 32+ character SECRET_KEY.
"""

import unittest
import os
import re
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestRenderHardening(unittest.TestCase):
    """Verifies render.yaml infrastructure declarations and web/main.py boot guard."""

    def test_render_yaml_configuration(self):
        """Verifies render.yaml contains required secrets and concurrency settings."""
        render_yaml_path = PROJECT_ROOT / "render.yaml"
        self.assertTrue(render_yaml_path.exists(), "render.yaml file does not exist")

        with open(render_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check workers 2 is in startCommand
        self.assertRegex(content, r"startCommand:\s*.*--workers 2", "render.yaml startCommand must configure --workers 2")

        # Check required secrets are declared with sync: false
        required_secrets = ["SECRET_KEY", "ADMIN_API_KEY", "ADMIN_PASSWORD"]
        for sec in required_secrets:
            pattern = rf"- key:\s*{sec}\s*\n\s*sync:\s*false"
            self.assertRegex(content, pattern, f"Secret {sec} in render.yaml must be declared with sync: false")

    def test_production_boot_guard_rejects_missing_secret_key(self):
        """Verifies that lifespan raises RuntimeError in production when SECRET_KEY is missing or too short."""
        from fastapi import FastAPI
        from web.main import lifespan

        test_app = FastAPI()

        # Case 1: Insecure default fallback salt
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "stock_research_user_session_salt_2026"}):
            with self.assertRaises(RuntimeError) as ctx:
                import asyncio
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("CRITICAL PRODUCTION BOOT FAILURE", str(ctx.exception))

        # Case 2: Short key (< 32 chars)
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "too_short_key_12345"}):
            with self.assertRaises(RuntimeError) as ctx:
                import asyncio
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("shorter than 32 characters", str(ctx.exception))

        # Case 3: Empty key
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                import asyncio
                async def run_boot():
                    async with lifespan(test_app):
                        pass
                asyncio.run(run_boot())
            self.assertIn("missing, insecure", str(ctx.exception))

    def test_production_boot_guard_accepts_valid_secret_key(self):
        """Verifies that lifespan passes successfully in production with a valid 32+ char key."""
        from fastapi import FastAPI
        from web.main import lifespan

        test_app = FastAPI()
        valid_key = "a" * 32  # 32-character key

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": valid_key, "TESTING": "1"}):
            import asyncio
            async def run_boot():
                async with lifespan(test_app):
                    pass
            # Should not raise RuntimeError
            asyncio.run(run_boot())


if __name__ == "__main__":
    unittest.main()

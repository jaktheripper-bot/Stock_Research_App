import unittest
from pathlib import Path
from unittest.mock import patch

import bse_master
import core.db.scrip_aliases as scrip_aliases
from core.db.connection import get_db_connection, init_db

TEST_ALIASES = ("ZZALIAS ONE", "ZZALIAS TWO")


class TestLearnedScripAliases(unittest.TestCase):
    """v052: learned ticker/name -> BSE scrip code aliases live in learned_scrip_aliases, not a JSON file."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self._purge()
        scrip_aliases.invalidate_cache()

    def tearDown(self):
        self._purge()
        scrip_aliases.invalidate_cache()

    def _purge(self):
        conn = get_db_connection()
        cur = conn.cursor()
        p = "%s" if scrip_aliases._is_pg() else "?"
        for alias in TEST_ALIASES:
            cur.execute(f"DELETE FROM learned_scrip_aliases WHERE alias = {p}", (alias,))
        conn.commit()
        cur.close()
        conn.close()

    def test_migration_imported_legacy_entries_without_junk(self):
        aliases = scrip_aliases.get_learned_aliases()
        self.assertEqual(aliases.get("PARAS HEALTHCARE"), "545005")
        self.assertEqual(aliases.get("TONBO"), "544999")
        self.assertFalse(any("{" in k or ":" in k for k in aliases))

    def test_save_and_read_round_trip_and_update(self):
        self.assertTrue(scrip_aliases.save_learned_alias("zzalias one", "512345"))
        self.assertEqual(scrip_aliases.get_learned_aliases().get("ZZALIAS ONE"), "512345")
        self.assertTrue(scrip_aliases.save_learned_alias("ZZALIAS ONE", "512346"))
        self.assertEqual(scrip_aliases.get_learned_aliases().get("ZZALIAS ONE"), "512346")

    def test_save_invalidates_cache_version(self):
        scrip_aliases.get_learned_aliases()
        before = scrip_aliases.cache_version()
        scrip_aliases.save_learned_alias("ZZALIAS TWO", "523456")
        self.assertGreater(scrip_aliases.cache_version(), before)
        self.assertIn("ZZALIAS TWO", scrip_aliases.get_learned_aliases())

    def test_rejects_junk_alias_and_invalid_codes(self):
        with self.assertLogs("equity_research.core.db.scrip_aliases", level="WARNING"):
            self.assertFalse(scrip_aliases.save_learned_alias("{'TICKER': 'MANALIPETC'}", "500268"))
        for bad_code in ("12345", "1234567", "ABCDEF", "", None):
            with self.subTest(code=bad_code):
                self.assertFalse(scrip_aliases.save_learned_alias("ZZALIAS ONE", bad_code))
        self.assertNotIn("ZZALIAS ONE", scrip_aliases.get_learned_aliases())

    def test_unverified_when_code_not_in_official_master(self):
        scrip_aliases.save_learned_alias("ZZALIAS ONE", "599999")
        conn = get_db_connection()
        cur = conn.cursor()
        p = "%s" if scrip_aliases._is_pg() else "?"
        cur.execute(f"SELECT verified, source FROM learned_scrip_aliases WHERE alias = {p}", ("ZZALIAS ONE",))
        verified, source = cur.fetchone()
        cur.close()
        conn.close()
        self.assertFalse(bool(verified))
        self.assertEqual(source, scrip_aliases.SOURCE_GEMINI)

    def test_resolver_uses_table_tier(self):
        scrip_aliases.save_learned_alias("ZZALIAS TWO", "534567")
        self.assertEqual(bse_master.resolve_bse_scrip_code("ZZALIAS TWO"), "534567")
        self.assertIn("ZZALIAS TWO", bse_master._get_cached_candidates())

    def test_database_failure_returns_empty_and_logs(self):
        with patch("core.db.connection.get_db_connection", side_effect=RuntimeError("db down")):
            with self.assertLogs("equity_research.core.db.scrip_aliases", level="WARNING"):
                self.assertEqual(scrip_aliases.get_learned_aliases(), {})
            with self.assertLogs("equity_research.core.db.scrip_aliases", level="WARNING"):
                self.assertFalse(scrip_aliases.save_learned_alias("ZZALIAS ONE", "512345"))

    def test_json_file_is_never_written(self):
        scrip_aliases.save_learned_alias("ZZALIAS ONE", "512345")
        legacy = Path("dynamic_aliases.json")
        self.assertFalse(legacy.exists() and "ZZALIAS ONE" in legacy.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

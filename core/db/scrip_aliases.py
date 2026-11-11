"""Learned BSE scrip aliases (ticker / company name -> 6-digit BSE scrip code).

Replaces the git-tracked ``dynamic_aliases.json`` file. Aliases are learned when every
other resolution tier fails and Gemini grounded search finds a code; they are stored in
``learned_scrip_aliases`` (Supabase PostgreSQL in production, SQLite locally) so every
machine and every Render deploy shares the same knowledge.

A learned code is always saved, but ``verified`` is true only when the code exists in the
official ``bse_scrip_master`` table. Nothing here fabricates entries: on database errors
readers get the last good cache (or an empty dict) and writers log and return False.
"""
import logging
import re
import threading
import time
from typing import Dict, Optional

from normalizer import clean_ticker

logger = logging.getLogger("equity_research.core.db.scrip_aliases")

LEARNED_ALIASES_TABLE = "learned_scrip_aliases"
SOURCE_GEMINI = "gemini_grounded_search"
SOURCE_LEGACY_JSON = "legacy_dynamic_aliases_json"
_CACHE_TTL_SECONDS = 300.0
_SCRIP_CODE_RE = re.compile(r"^[0-9]{6}$")

# Contents of dynamic_aliases.json at retirement (2026-11-11), imported once by migration v052.
# The junk key the file also held (a stringified MANALIPETC stock record) is deliberately absent.
LEGACY_DYNAMIC_ALIASES: Dict[str, str] = {
    "INDY": "535789",
    "MRS BECTORS": "543253",
    "ALTIUSINVIT": "543225",
    "SUVENPHAR": "543064",
    "KPIENERGY": "542323",
    "COASTAL CORP": "501831",
    "GODAVARI POWER": "532734",
    "GUJRAT THEMIS BIOSYN": "506879",
    "PIX TRANSMISSION": "500333",
    "TATA TELECOM": "500463",
    "ZINDAL WORLDWIDE": "531543",
    "AMIORG": "543349",
    "ICICILIFE": "540133",
    "NSC": "544937",
    "JPL": "545004",
    "ZETWERK": "545000",
    "JIO PLATFORMS": "545004",
    "ZETWERK MANUFACTURING BUSINESSES": "545000",
    "BONFIG": "544996",
    "PARASHLTH": "545005",
    "BONFIGLIOLI TRANSMISSIONS": "544996",
    "PARAS HEALTHCARE": "545005",
    "TONBO": "544999",
    "TONBO IMAGING INDIA": "544999",
}

_cache_lock = threading.Lock()
_cache: Dict[str, object] = {"data": None, "loaded_at": 0.0, "version": 0}


def normalize_alias(alias: str) -> Optional[str]:
    """Returns the canonical alias key, or None when the input is not a clean ticker/name."""
    if not isinstance(alias, str) or "{" in alias or ":" in alias:
        return None  # serialized objects (e.g. "{'TICKER': ...}") are never aliases
    cleaned = clean_ticker(alias)
    if not cleaned or not re.fullmatch(r"[A-Z0-9][A-Z0-9 &.\-']{0,79}", cleaned):
        return None
    return cleaned


def is_valid_scrip_code(code) -> bool:
    return bool(_SCRIP_CODE_RE.match(str(code or "").strip()))


def cache_version() -> int:
    """Monotonic version bumped on every reload/write; used to key dependent caches."""
    return int(_cache["version"])


def invalidate_cache() -> None:
    with _cache_lock:
        _cache["data"] = None
        _cache["loaded_at"] = 0.0
        _cache["version"] = int(_cache["version"]) + 1


def _is_pg() -> bool:
    from core.db.connection import get_supabase_url

    return bool(get_supabase_url())


def _table_exists(cursor, table: str, is_pg: bool) -> bool:
    if is_pg:
        cursor.execute("SELECT to_regclass(%s);", (f"public.{table}",))
        row = cursor.fetchone()
        return bool(row and row[0])
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
    return cursor.fetchone() is not None


def _code_in_official_master(cursor, scrip_code: str, is_pg: bool) -> bool:
    if not _table_exists(cursor, "bse_scrip_master", is_pg):
        return False
    p = "%s" if is_pg else "?"
    cursor.execute(f"SELECT 1 FROM bse_scrip_master WHERE scrip_code = {p} LIMIT 1;", (scrip_code,))
    return cursor.fetchone() is not None


def create_learned_aliases_table(cursor, is_pg: bool) -> None:
    """DDL for migration v052 (idempotent)."""
    if is_pg:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {LEARNED_ALIASES_TABLE} (
                alias TEXT PRIMARY KEY,
                scrip_code VARCHAR(6) NOT NULL CHECK (scrip_code ~ '^[0-9]{{6}}$'),
                source TEXT NOT NULL DEFAULT '{SOURCE_GEMINI}',
                verified BOOLEAN NOT NULL DEFAULT FALSE,
                learned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_verified_at TIMESTAMPTZ
            );
            """
        )
    else:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {LEARNED_ALIASES_TABLE} (
                alias TEXT PRIMARY KEY,
                scrip_code TEXT NOT NULL CHECK (length(scrip_code) = 6 AND scrip_code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'),
                source TEXT NOT NULL DEFAULT '{SOURCE_GEMINI}',
                verified INTEGER NOT NULL DEFAULT 0,
                learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TEXT
            );
            """
        )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_learned_scrip_aliases_code ON {LEARNED_ALIASES_TABLE}(scrip_code);"
    )


def _upsert_on_cursor(cursor, alias: str, scrip_code: str, source: str, is_pg: bool, overwrite: bool) -> None:
    verified = _code_in_official_master(cursor, scrip_code, is_pg)
    p = "%s" if is_pg else "?"
    now_expr = "now()" if is_pg else "CURRENT_TIMESTAMP"
    verified_at = now_expr if verified else "NULL"
    verified_val = verified if is_pg else int(verified)
    conflict = (
        f"DO UPDATE SET scrip_code = EXCLUDED.scrip_code, source = EXCLUDED.source, "
        f"verified = EXCLUDED.verified, last_verified_at = EXCLUDED.last_verified_at, learned_at = {now_expr}"
        if overwrite
        else "DO NOTHING"
    )
    cursor.execute(
        f"""
        INSERT INTO {LEARNED_ALIASES_TABLE} (alias, scrip_code, source, verified, last_verified_at)
        VALUES ({p}, {p}, {p}, {p}, {verified_at})
        ON CONFLICT (alias) {conflict};
        """,
        (alias, scrip_code, source, verified_val),
    )


def import_legacy_aliases(cursor, is_pg: bool, entries: Optional[Dict[str, str]] = None) -> int:
    """Migration v052 one-time import; never overwrites an alias already in the table."""
    imported = 0
    for raw_alias, raw_code in (entries if entries is not None else LEGACY_DYNAMIC_ALIASES).items():
        alias = normalize_alias(raw_alias)
        code = str(raw_code or "").strip()
        if not alias or not is_valid_scrip_code(code):
            logger.warning("Skipping invalid legacy scrip alias %r -> %r", str(raw_alias)[:60], raw_code)
            continue
        _upsert_on_cursor(cursor, alias, code, SOURCE_LEGACY_JSON, is_pg, overwrite=False)
        imported += 1
    return imported


def get_learned_aliases() -> Dict[str, str]:
    """Returns {alias: scrip_code}; serves the last good copy (or {}) if the database is unavailable."""
    with _cache_lock:
        data = _cache["data"]
        if data is not None and (time.monotonic() - float(_cache["loaded_at"])) < _CACHE_TTL_SECONDS:
            return data  # type: ignore[return-value]
    conn = cur = None
    try:
        from core.db.connection import get_db_connection

        is_pg = _is_pg()
        conn = get_db_connection()
        cur = conn.cursor()
        if not _table_exists(cur, LEARNED_ALIASES_TABLE, is_pg):
            fresh: Dict[str, str] = {}
        else:
            cur.execute(f"SELECT alias, scrip_code FROM {LEARNED_ALIASES_TABLE};")
            fresh = {str(a): str(c).strip() for a, c in cur.fetchall() if a and is_valid_scrip_code(c)}
        with _cache_lock:
            if fresh != _cache["data"]:
                _cache["version"] = int(_cache["version"]) + 1
            _cache["data"] = fresh
            _cache["loaded_at"] = time.monotonic()
        return fresh
    except Exception as exc:
        logger.warning("Learned scrip alias lookup unavailable; serving last cached copy: %s", exc)
        with _cache_lock:
            return dict(_cache["data"] or {})  # type: ignore[arg-type]
    finally:
        for obj in (cur, conn):
            if obj is not None:
                try:
                    obj.close()
                except Exception as close_err:
                    logger.debug("Scrip alias connection close notice: %s", close_err)


def save_learned_alias(alias: str, scrip_code: str, source: str = SOURCE_GEMINI) -> bool:
    """Upserts a learned alias; returns True on success. Invalid input is rejected, not coerced."""
    clean_alias = normalize_alias(alias)
    code = str(scrip_code or "").strip()
    if not clean_alias or not is_valid_scrip_code(code):
        logger.warning("Rejected learned scrip alias %r -> %r (invalid alias or code)", str(alias)[:60], scrip_code)
        return False
    conn = cur = None
    try:
        from core.db.connection import get_db_connection

        is_pg = _is_pg()
        conn = get_db_connection()
        cur = conn.cursor()
        create_learned_aliases_table(cur, is_pg)
        _upsert_on_cursor(cur, clean_alias, code, source, is_pg, overwrite=True)
        conn.commit()
        invalidate_cache()
        return True
    except Exception as exc:
        logger.warning("Could not save learned scrip alias %s -> %s: %s", clean_alias, code, exc)
        if conn is not None:
            try:
                conn.rollback()
            except Exception as rb_err:
                logger.debug("Scrip alias rollback notice: %s", rb_err)
        return False
    finally:
        for obj in (cur, conn):
            if obj is not None:
                try:
                    obj.close()
                except Exception as close_err:
                    logger.debug("Scrip alias connection close notice: %s", close_err)

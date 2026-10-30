#!/usr/bin/env bash
# ==============================================================================
# Autonomous Local Multi-Asset Daily Audit & Cloud-to-Local Catch-Up Wrapper
# 1. Pulls fresh cloud-scheduled records from Supabase into local reports.db
# 2. Audits all 8 multi-asset domains in reports.db against TTL/coverage SLAs
# 3. Executes targeted local catch-up (SUPABASE_DB_URL="") for any missing items
# 4. Pushes remediated local records back to Supabase for 100% parity
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON="$ROOT_DIR/.venv/bin/python"
elif [ -x "$ROOT_DIR/venv/bin/python" ]; then
    PYTHON="$ROOT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

TARGET_DATE=""
DB_PATH_OVERRIDE=""
DRY_RUN=0
SKIP_PUSH=0
SKIP_PULL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --date)
            TARGET_DATE="${2:-}"
            shift 2
            ;;
        --db-path)
            DB_PATH_OVERRIDE="${2:-}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --skip-push)
            SKIP_PUSH=1
            shift
            ;;
        --skip-pull)
            SKIP_PULL=1
            shift
            ;;
        -h|--help)
            echo "Usage: scripts/run_local_daily_audit.sh [--date YYYY-MM-DD] [--db-path PATH] [--dry-run] [--skip-pull] [--skip-push]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

TARGET_DB="${DB_PATH_OVERRIDE:-$ROOT_DIR/reports.db}"

# Default target date: if >= 09:05 IST, audit today's morning+prior nightly state;
# before 09:05 IST (e.g., midnight 00:00 IST audit), audit the just-completed IST day.
if [ -z "$TARGET_DATE" ]; then
    TARGET_DATE=$("$PYTHON" -c '
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Asia/Kolkata"))
target = now.date() if (now.hour > 9 or (now.hour == 9 and now.minute >= 5)) else (now - timedelta(days=1)).date()
print(target.isoformat())
')
fi

NOW_IST=$(TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S IST")
echo "=============================================================================="
echo "Moatnomics Local Multi-Asset Audit & Catch-Up | $NOW_IST"
echo "Target Edition Date : $TARGET_DATE"
echo "Target SQLite DB    : $TARGET_DB"
echo "Mode                : $([ "$DRY_RUN" -eq 1 ] && echo 'DRY-RUN' || echo 'LIVE REMEDIATION')"
echo "=============================================================================="

# ------------------------------------------------------------------------------
# Phase 1: Pull cloud-generated cohorts from Supabase -> local SQLite
# ------------------------------------------------------------------------------
if [ "$SKIP_PULL" -eq 0 ]; then
    echo "--> [Phase 1/4] Syncing latest multi-asset records from Supabase..."
    PULL_ARGS=(--db-path "$TARGET_DB")
    if [ "$DRY_RUN" -eq 1 ]; then
        PULL_ARGS+=(--dry-run)
    fi
    "$PYTHON" "$ROOT_DIR/scripts/sync_from_supabase.py" "${PULL_ARGS[@]}" || \
        echo "[WARN] Supabase pull reported an error; continuing with local SQLite inspection."
else
    echo "--> [Phase 1/4] Skipping Supabase pull (--skip-pull)."
fi

# ------------------------------------------------------------------------------
# Phase 2: Inspect all 8 multi-asset domains in TARGET_DB for SLA gaps
# ------------------------------------------------------------------------------
echo "--> [Phase 2/4] Auditing 8 multi-asset domains in $TARGET_DB for $TARGET_DATE..."
GAP_JSON=$("$PYTHON" - "$TARGET_DB" "$TARGET_DATE" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.presentation.formatters import _coerce_datetime

db_path = sys.argv[1]
target_date = sys.argv[2]
ist = ZoneInfo("Asia/Kolkata")
now_ist = datetime.now(ist)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

def count_stale(rows, days):
    cutoff = now_ist - timedelta(days=days)
    stale = 0
    for (ts_val,) in rows:
        dt = _coerce_datetime(ts_val)
        if dt is None or dt < cutoff:
            stale += 1
    return stale

# 1. Institutional Equity Dossiers (14-day TTL, >=500 chars)
rep_rows = cur.execute("SELECT ticker, LENGTH(TRIM(COALESCE(report_text, ''))), timestamp FROM reports").fetchall()
short_reports = [r[0] for r in rep_rows if (r[1] or 0) < 500]
stale_reports = count_stale([(r[2],) for r in rep_rows], 14)

# 2. Stock Discovery & Daily 15-Stock Ingestion
disc_tickers = [
    r[0] for r in cur.execute(
        "SELECT ticker FROM discovery_reel WHERE substr(edition_date, 1, 10) = ? AND is_active = 1",
        (target_date,),
    ).fetchall()
]
compiled_set = {r[0] for r in rep_rows if (r[1] or 0) >= 500}
unbacked_disc = [t for t in disc_tickers if t not in compiled_set]

# 3. Mutual Funds & Forensic Look-Through
mf_ts = cur.execute("SELECT MAX(last_updated) FROM mutual_fund_schemes").fetchone()[0]
mf_stale = count_stale([(mf_ts,)], 2) if mf_ts else 1
unaudited_funds = [
    r[0] for r in cur.execute("""
        SELECT DISTINCT h.scheme_code
        FROM mutual_fund_holdings h
        LEFT JOIN fund_forensic_dossiers f ON f.scheme_code = h.scheme_code
        WHERE f.scheme_code IS NULL OR TRIM(COALESCE(f.dossier_text, '')) = ''
        ORDER BY h.scheme_code
    """).fetchall()
]

# 4. Corporate Debt Surveillance
debt_ts = cur.execute("SELECT MAX(last_updated) FROM corporate_debt_securities").fetchone()[0]
debt_stale = count_stale([(debt_ts,)], 2) if debt_ts else 1

# 5. Sovereign Curve & Benchmarks
sov_tenors = cur.execute(
    "SELECT COUNT(*) FROM sovereign_curve_history WHERE snapshot_key = ?",
    (target_date,),
).fetchone()[0]

# 6. REITs, InvITs, SGBs & Alternative Yield (90-day TTL)
alt_stale = (
    count_stale(cur.execute("SELECT updated_at FROM reits_and_invits").fetchall(), 90)
    + count_stale(cur.execute("SELECT updated_at FROM sgb_tranches").fetchall(), 90)
    + count_stale(cur.execute("SELECT updated_at FROM alternative_yield_products").fetchall(), 90)
)

# 7. National ETF Matrix
etf_ts = cur.execute("SELECT MAX(updated_at) FROM etf_matrix").fetchone()[0]
etf_stale = count_stale([(etf_ts,)], 2) if etf_ts else 1

# 8. Unlisted MSME & SME Forensic Dossiers (15-firm daily cohort & 30-day TTL)
msme_cohort = cur.execute(
    "SELECT COUNT(*) FROM msme_firms WHERE substr(last_updated, 1, 10) >= ?",
    (target_date,),
).fetchone()[0]
msme_stale = count_stale(cur.execute("SELECT last_updated FROM msme_firms").fetchall(), 30)

conn.close()

gaps = {
    "need_morning": (len(disc_tickers) < 15 or len(unbacked_disc) > 0 or msme_cohort < 15),
    "need_nightly": (mf_stale > 0 or debt_stale > 0 or sov_tenors < 16 or etf_stale > 0 or alt_stale > 0),
    "need_reports_refresh": (len(short_reports) > 0 or stale_reports > 0),
    "unaudited_funds": unaudited_funds,
    "details": {
        "reports_total": len(rep_rows),
        "short_reports": len(short_reports),
        "stale_reports_14d": stale_reports,
        "discovery_count": len(disc_tickers),
        "discovery_unbacked": len(unbacked_disc),
        "unaudited_funds_count": len(unaudited_funds),
        "sovereign_tenors_for_date": sov_tenors,
        "msme_cohort_for_date": msme_cohort,
        "msme_stale_30d": msme_stale,
        "alt_stale_90d": alt_stale,
    },
}
print(json.dumps(gaps))
PY
)

echo "    Audit Snapshot: $GAP_JSON"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "--> [Dry-Run] Exiting without mutating $TARGET_DB."
    exit 0
fi

# ------------------------------------------------------------------------------
# Phase 3: Execute targeted local catch-up pipelines (SUPABASE_DB_URL="")
# ------------------------------------------------------------------------------
REMEDIATED=0

NEED_MORNING=$("$PYTHON" -c "import json,sys; print(1 if json.loads(sys.argv[1])['need_morning'] else 0)" "$GAP_JSON")
NEED_NIGHTLY=$("$PYTHON" -c "import json,sys; print(1 if json.loads(sys.argv[1])['need_nightly'] else 0)" "$GAP_JSON")
NEED_REP_REFRESH=$("$PYTHON" -c "import json,sys; print(1 if json.loads(sys.argv[1])['need_reports_refresh'] else 0)" "$GAP_JSON")
UNAUDITED_FUNDS=$("$PYTHON" -c "import json,sys; print(' '.join(json.loads(sys.argv[1])['unaudited_funds']))" "$GAP_JSON")

echo "--> [Phase 3/4] Running targeted local catch-up pipelines..."

if [ "$NEED_MORNING" -eq 1 ]; then
    echo "    [Catch-Up] Running morning pipeline locally for $TARGET_DATE..."
    FORCE_LOCAL_SQLITE=1 SUPABASE_DB_URL="" DB_PATH="$TARGET_DB" \
        "$PYTHON" "$ROOT_DIR/scripts/run_scheduled_pipeline.py" --mode morning --date "$TARGET_DATE" --force
    REMEDIATED=1
fi

if [ "$NEED_NIGHTLY" -eq 1 ]; then
    echo "    [Catch-Up] Running nightly pipeline locally for $TARGET_DATE..."
    FORCE_LOCAL_SQLITE=1 SUPABASE_DB_URL="" DB_PATH="$TARGET_DB" \
        "$PYTHON" "$ROOT_DIR/scripts/run_scheduled_pipeline.py" --mode nightly --date "$TARGET_DATE" --force
    REMEDIATED=1
fi

if [ -n "$UNAUDITED_FUNDS" ]; then
    for SCHEME_CODE in $UNAUDITED_FUNDS; do
        echo "    [Catch-Up] Auditing portfolio-backed mutual fund: $SCHEME_CODE..."
        FORCE_LOCAL_SQLITE=1 SUPABASE_DB_URL="" DB_PATH="$TARGET_DB" \
            "$PYTHON" "$ROOT_DIR/scripts/run_daily_fund_audit.py" --scheme "$SCHEME_CODE"
        REMEDIATED=1
    done
fi

if [ "$NEED_REP_REFRESH" -eq 1 ]; then
    echo "    [Catch-Up] Refreshing stale equity baselines in $TARGET_DB..."
    FORCE_LOCAL_SQLITE=1 SUPABASE_DB_URL="" DB_PATH="$TARGET_DB" \
        "$PYTHON" "$ROOT_DIR/scripts/update_all_reports.py"
    REMEDIATED=1
fi

if [ "$REMEDIATED" -eq 0 ]; then
    echo "    All 8 multi-asset domains already satisfy freshness & coverage SLAs."
fi

# ------------------------------------------------------------------------------
# Phase 4: Push local catch-up updates back to Supabase
# ------------------------------------------------------------------------------
if [ "$REMEDIATED" -eq 1 ] && [ "$SKIP_PUSH" -eq 0 ]; then
    echo "--> [Phase 4/4] Syncing remediated local records back to Supabase..."
    "$PYTHON" "$ROOT_DIR/scripts/sync_to_supabase.py" --db-path "$TARGET_DB" || \
        echo "[WARN] Supabase push reported an error; local SQLite updates remain safely persisted."
else
    echo "--> [Phase 4/4] No outbound Supabase push required."
fi

echo "✅ Local Daily Multi-Asset Audit Complete."

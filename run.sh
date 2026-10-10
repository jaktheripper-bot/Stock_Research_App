#!/usr/bin/env bash
# ==============================================================================
# Unified CLI Task Runner for Stock Research App
# Automatically resolves .venv/bin/python and executes standardized workflows
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve virtual environment Python
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi

COMMAND="${1:-test}"

case "$COMMAND" in
    lint)
        echo "--> [1/1] Running System Contract & Integrity Audit..."
        "$PYTHON" check_system.py
        ;;
    test)
        echo "--> [1/2] Running System Integrity & Contract Audit..."
        "$PYTHON" check_system.py
        echo "--> [2/2] Running Regression Test Suite..."
        "$PYTHON" -m unittest discover -s tests
        echo "✅ All tests passed successfully."
        ;;
    bench)
        echo "--> Running Performance Benchmark..."
        "$PYTHON" benchmark.py
        ;;
    preflight)
        echo "--> [1/3] Running System Integrity Audit..."
        "$PYTHON" check_system.py
        echo "--> [2/3] Running Regression Test Suite..."
        "$PYTHON" -m unittest discover -s tests
        echo "--> [3/3] Enforcing Latency & Performance Budget..."
        "$PYTHON" benchmark.py
        echo "🎉 PRE-FLIGHT VALIDATION COMPLETE. Ready for deployment."
        ;;
    start|web)
        echo "--> Starting High-Performance FastAPI SSR Web Server on http://localhost:8000..."
        "$PYTHON" -m uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    backup)
        echo "--> Creating site backup (web assets + DB)..."
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        BACKUP_DIR="${SCRIPT_DIR}/backups/${TIMESTAMP}"
        mkdir -p "${BACKUP_DIR}"
        tar -czf "${BACKUP_DIR}/site_assets.tar.gz" web/ reports.db
        echo "✅ Backup stored in ${BACKUP_DIR}"
        ;;
    admin)
        echo "--> Admin console is native SSR in FastAPI. Access at http://localhost:8000/admin"
        echo "--> Starting server..."
        "$PYTHON" -m uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    live-audit|live_audit|audit-live)
        echo "--> [1/1] Executing Real Browser Interaction Audit on Live Deployment..."
        "$PYTHON" test_live_ui.py
        ;;
    mf-ingest)
        shift
        echo "--> Ingesting top mutual fund portfolio disclosures..."
        "$PYTHON" scripts/ingest_mf_portfolios.py "$@"
        ;;
    checkpoint)
        shift
        echo "--> [1/1] Managing Release Checkpoint Creation..."
        "$PYTHON" ci/checkpoint_manager.py create "$@"
        ;;
    rollback)
        shift
        echo "--> [1/1] Initiating Production Disaster Recovery Rollback..."
        "$PYTHON" ci/checkpoint_manager.py rollback "$@"
        ;;
    checkpoints|list-checkpoints)
        shift
        "$PYTHON" ci/checkpoint_manager.py list "$@"
        ;;
    nifty100|nifty-100)
        shift
        echo "--> Initiating Nifty 100 Institutional Research Generation Pipeline..."
        "$PYTHON" scripts/generate_nifty100_reports.py "$@"
        ;;
    sync-supabase|supabase-sync)
        shift
        echo "--> Syncing local research reports to Supabase..."
        "$PYTHON" scripts/sync_to_supabase.py "$@"
        ;;
    dump-chat|backup-chat|dump-session)
        shift
        echo "--> Creating formatted conversation transcript & session ledger dump..."
        "$PYTHON" scripts/dump_conversation.py "$@"
        ;;
    update-reports|refresh-reports)
        shift
        echo "--> Updating all reports in reports.db with exchange data and syncing..."
        "$PYTHON" scripts/update_all_reports.py "$@"
        ;;
    *)
        echo "Usage: ./run.sh [lint | test | bench | preflight | live-audit | start | web | admin | mf-ingest | nifty100 | sync-supabase | update-reports | dump-chat | checkpoint | rollback | checkpoints]"
        exit 1
        ;;
esac


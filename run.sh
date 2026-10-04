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
    STREAMLIT="$SCRIPT_DIR/.venv/bin/streamlit"
elif [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
    STREAMLIT="$SCRIPT_DIR/venv/bin/streamlit"
else
    PYTHON="python3"
    STREAMLIT="streamlit"
fi

COMMAND="${1:-test}"

case "$COMMAND" in
    lint)
        echo "--> [1/1] Running Streamlit Static Linter & Guardrails..."
        "$PYTHON" lint_streamlit.py
        ;;
    test)
        echo "--> [1/3] Running Streamlit Static Linter..."
        "$PYTHON" lint_streamlit.py
        echo "--> [2/3] Running System Integrity & Contract Audit..."
        "$PYTHON" check_system.py
        echo "--> [3/3] Running Interactive UI Simulation Suite..."
        "$PYTHON" test_ui_headless.py
        echo "✅ All tests passed successfully."
        ;;
    bench)
        echo "--> Running Performance Benchmark..."
        "$PYTHON" benchmark.py
        ;;
    preflight)
        echo "--> [1/4] Running Streamlit Static Linter..."
        "$PYTHON" lint_streamlit.py
        echo "--> [2/4] Running System Integrity Audit..."
        "$PYTHON" check_system.py
        echo "--> [3/4] Running Interactive UI Action Simulation..."
        "$PYTHON" test_ui_headless.py
        echo "--> [4/4] Enforcing Latency & Performance Budget..."
        "$PYTHON" benchmark.py
        echo "🎉 PRE-FLIGHT VALIDATION COMPLETE. Ready for deployment."
        ;;
    start)
        echo "--> Starting Streamlit Dev Server on http://localhost:8501..."
        "$STREAMLIT" run app.py
        ;;
    web)
        echo "--> Starting High-Performance FastAPI SSR Web Server on http://localhost:8000..."
        "$PYTHON" -m uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    backup)
        echo "--\> Creating site backup (static assets + DB)..."
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        BACKUP_DIR="${SCRIPT_DIR}/backups/${TIMESTAMP}"
        mkdir -p "${BACKUP_DIR}"
        tar -czf "${BACKUP_DIR}/site_assets.tar.gz" static/ templates/ app.py
        echo "✅ Backup stored in ${BACKUP_DIR}"
        ;;
    admin)
        echo "--> Starting Private Admin Portal on http://localhost:8502..."
        "$STREAMLIT" run admin.py --server.port 8502
        ;;
    live-audit|live_audit|audit-live)
        echo "--> [1/1] Executing Real Browser Interaction Audit on Live Deployment..."
        "$PYTHON" test_live_ui.py
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
    *)
        echo "Usage: ./run.sh [lint | test | bench | preflight | live-audit | start | web | admin | checkpoint | rollback | checkpoints]"
        exit 1
        ;;
esac


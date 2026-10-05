#!/usr/bin/env bash
# scripts/backup.sh – creates a timestamped backup of the application database and codebase

set -euo pipefail

BACKUP_DIR="${PWD}/backups"
mkdir -p "${BACKUP_DIR}"

# Timestamp in IST (YYYYMMDD_HHMMSS)
TIMESTAMP=$(TZ=Asia/Kolkata date '+%Y%m%d_%H%M%S')
ARCHIVE_NAME="app_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_DIR}/${ARCHIVE_NAME}"

echo "📦 Creating application backup archive..."

# Exclude large/transient directories and secrets
tar --exclude="./.git" \
    --exclude="./__pycache__" \
    --exclude="./.pytest_cache" \
    --exclude="./backups" \
    --exclude="./.tmp.driveupload" \
    --exclude="*.tar.gz" \
    --exclude="./.streamlit/secrets.toml" \
    --exclude="./.env" \
    -czf "${ARCHIVE_PATH}" .

echo "✅ Backup archive created at ${ARCHIVE_PATH} ($(du -h "${ARCHIVE_PATH}" | cut -f1))"

# Also back up reports.db snapshot specifically if it exists
if [[ -f "reports.db" ]]; then
  DB_BACKUP_PATH="${BACKUP_DIR}/reports_db_${TIMESTAMP}.sqlite"
  cp "reports.db" "${DB_BACKUP_PATH}"
  echo "✅ SQLite database snapshot created at ${DB_BACKUP_PATH}"
fi

# Upload to Supabase storage if credentials exist
if [[ -n "${SUPABASE_URL:-}" && -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  STORAGE_URL="${SUPABASE_URL%/}/storage/v1/object/backups/${ARCHIVE_NAME}"
  echo "Uploading backup to Supabase storage..."
  curl -X POST "${STORAGE_URL}" \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@${ARCHIVE_PATH}" \
    --silent --show-error || echo "⚠️ Supabase upload encountered an issue"
  echo "✅ Upload attempt to Supabase complete"
else
  echo "ℹ️ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set – stored locally in ${BACKUP_DIR}"
fi
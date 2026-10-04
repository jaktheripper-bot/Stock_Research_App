#!/usr/bin/env bash

# scripts/backup.sh – creates a timestamped backup of the built site and uploads to Supabase storage

set -euo pipefail

# Adjust these paths if your build output directory differs
BUILD_DIR="${PWD}/dist"
BACKUP_DIR="${PWD}/backups"
mkdir -p "${BACKUP_DIR}"

# Timestamp in IST (YYYYMMDD_HHMMSS)
TIMESTAMP=$(TZ=Asia/Kolkata date '+%Y%m%d_%H%M%S')
ARCHIVE_NAME="site_backup_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_DIR}/${ARCHIVE_NAME}"

# Create the archive
if [[ -d "${BUILD_DIR}" ]]; then
  tar -czf "${ARCHIVE_PATH}" -C "${BUILD_DIR}" .
  echo "✅ Backup archive created at ${ARCHIVE_PATH}"
else
  echo "⚠️ Build directory ${BUILD_DIR} not found – nothing to back up"
  exit 1
fi

# Upload to Supabase storage (requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars)
if [[ -n "${SUPABASE_URL:-}" && -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  # Ensure URL does not end with a slash
  STORAGE_URL="${SUPABASE_URL%/}/storage/v1/object/backups/${ARCHIVE_NAME}"
  echo "Uploading backup to Supabase storage..."
  curl -X POST "${STORAGE_URL}" \
    -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@${ARCHIVE_PATH}" \
    --silent --show-error
  echo "✅ Uploaded to Supabase bucket 'backups'"
else
  echo "⚠️ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set – skipping upload"
fi
EOS && chmod +x scripts/backup.sh
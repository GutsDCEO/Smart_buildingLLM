#!/usr/bin/env bash
# ============================================================
# Smart Building AI — Automated Backup Script
# ============================================================
# Backs up:
#   1. PostgreSQL database (pg_dump)
#   2. Qdrant vector store (docker cp fallback)
#   3. .env file (copy)
#
# Usage: ./scripts/backup.sh
# Scheduled: Daily at 3:00 AM via launchd
# Retention: 14 days
# ============================================================
set -euo pipefail

# ── Configuration ────────────────────────────────────────────
PROJECT_DIR="/Users/mac/Smart_buildingLLM"
BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS=14
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/${TIMESTAMP}"

# ── Setup ────────────────────────────────────────────────────
mkdir -p "${BACKUP_SUBDIR}"
echo "[$(date)] Starting backup to ${BACKUP_SUBDIR}"

# ── 1. PostgreSQL Backup ────────────────────────────────────
echo "[$(date)] Backing up PostgreSQL..."
docker exec sb_postgres pg_dump \
    -U "${POSTGRES_USER:-smartbuilding}" \
    -d "${POSTGRES_DB:-smartbuilding_metadata}" \
    --format=custom \
    --compress=9 \
    > "${BACKUP_SUBDIR}/postgres_${TIMESTAMP}.dump"
echo "[$(date)] PostgreSQL backup complete ($(du -h "${BACKUP_SUBDIR}/postgres_${TIMESTAMP}.dump" | cut -f1))"

# ── 2. Qdrant Snapshot ──────────────────────────────────────
echo "[$(date)] Creating Qdrant backup..."
# Since Qdrant port is not exposed to host, use docker cp
docker cp sb_qdrant:/qdrant/storage "${BACKUP_SUBDIR}/qdrant_storage"
echo "[$(date)] Qdrant storage copied."

# ── 3. Environment File Backup ──────────────────────────────
echo "[$(date)] Backing up .env file..."
cp "${PROJECT_DIR}/.env" "${BACKUP_SUBDIR}/env_${TIMESTAMP}.bak"

# ── 4. Cleanup Old Backups ──────────────────────────────────
echo "[$(date)] Removing backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \;

# ── Summary ─────────────────────────────────────────────────
TOTAL_SIZE=$(du -sh "${BACKUP_SUBDIR}" | cut -f1)
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Backup Complete: ${BACKUP_SUBDIR}"
echo "  Total Size: ${TOTAL_SIZE}"
echo "  Contents:"
ls -lh "${BACKUP_SUBDIR}/" | tail -n +2
echo "═══════════════════════════════════════════════════════"
echo "[$(date)] Done."

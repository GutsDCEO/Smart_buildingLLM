#!/usr/bin/env bash
# ============================================================
# Generate production-grade secrets for .env
# Usage: ./scripts/generate-prod-secrets.sh
# ============================================================
set -euo pipefail

echo "# ── Production Secrets (generated $(date -u +%Y-%m-%dT%H:%M:%SZ)) ──"
echo ""
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '\n')"
echo "JWT_SECRET_KEY=$(openssl rand -hex 64)"
echo "N8N_BASIC_AUTH_PASSWORD=$(openssl rand -base64 24 | tr -d '\n')"
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)"
echo ""
echo "# ── How to Apply ──"
echo "# 1. Copy the values above into your .env file"
echo "# 2. If FRESH deployment:  docker compose down && docker compose up -d --build"
echo "# 3. If EXISTING data:     also update Postgres password internally:"
echo "#    docker exec -it sb_postgres psql -U smartbuilding -c \"ALTER USER smartbuilding PASSWORD 'NEW_PASSWORD';\""

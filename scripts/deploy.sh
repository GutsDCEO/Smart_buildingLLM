#!/usr/bin/env bash
# ============================================================
# Smart Building AI Assistant — Production Deployment Script
# ============================================================
# Usage: ./scripts/deploy.sh
# Runs on the Mac Mini production server.
# ============================================================

set -euo pipefail

echo "============================================================"
echo "🚀 Starting Production Deployment for Smart Building AI"
echo "============================================================"

# 1. Ensure .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please run ./scripts/generate-prod-secrets.sh first to generate production secrets."
    exit 1
fi

# 2. Pull latest main branch
echo "📥 Pulling latest updates from GitHub..."
git pull origin main

# 3. Deploy/restart containers using base + production override
echo "🐳 Deploying production Docker Compose stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans

# 4. Show status
echo "============================================================"
echo "✅ Production Deployment Complete!"
echo "============================================================"
echo "Web UI:     http://smart-building.local/"
echo "API:        http://smart-building.local/api/"
echo "n8n UI:     http://smart-building.local/n8n/"
echo "============================================================"

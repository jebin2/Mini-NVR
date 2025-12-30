#!/bin/bash
# ============================================
# Generate Web Config from .env
# ============================================
# Injects environment variables into web/js/config.js
# Usage: ./scripts/generate-web-config.sh
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="${PROJECT_ROOT}/web/js/config.js"
ENV_FILE="${PROJECT_ROOT}/.env"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check .env exists
if [ ! -f "$ENV_FILE" ]; then
    log_error ".env file not found. Copy .env.example to .env first."
    exit 1
fi

# Load .env
set -a
source "$ENV_FILE"
set +a

# Defaults for optional variables
GO2RTC_API_PORT="${GO2RTC_API_PORT:-2127}"
WEB_PORT="${WEB_PORT:-2126}"

log_info "Generating web/js/config.js..."

cat > "$OUTPUT_FILE" << EOF
// AUTO-GENERATED from .env - Do not edit manually
// Regenerate: ./scripts/generate-web-config.sh

export const CONFIG = {
    apiBase: '/api',
    webPort: ${WEB_PORT},
    gridRefreshInterval: 10000,
    storageRefreshInterval: 60000,
    liveThresholdSeconds: 15
};
EOF

log_info "Generated: $OUTPUT_FILE (go2rtcPort: ${GO2RTC_API_PORT})"

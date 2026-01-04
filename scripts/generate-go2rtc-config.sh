#!/bin/bash
# ============================================
# Generate go2rtc Configuration from .env
# ============================================
# Usage: ./scripts/generate-go2rtc-config.sh
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="${PROJECT_ROOT}/go2rtc.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
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

# Validate required variables
for var in DVR_IP DVR_USER DVR_PASS DVR_PORT NUM_CHANNELS RTSP_URL_TEMPLATE; do
    if [ -z "${!var}" ]; then
        log_error "Required variable $var is not set in .env"
        exit 1
    fi
done

# Defaults for optional variables
GO2RTC_API_PORT="${GO2RTC_API_PORT}"
GO2RTC_WEBRTC_PORT="${GO2RTC_WEBRTC_PORT}"
GO2RTC_RTSP_PORT="${GO2RTC_RTSP_PORT}"

log_info "Generating go2rtc.yaml..."

# Generate RTSP URL for a channel
generate_url() {
    local ch=$1 url="$RTSP_URL_TEMPLATE"
    url="${url//\{user\}/$DVR_USER}"
    url="${url//\{pass\}/$DVR_PASS}"
    url="${url//\{ip\}/$DVR_IP}"
    url="${url//\{port\}/$DVR_PORT}"
    url="${url//\{channel\}/$ch}"
    echo "$url"
}

# Write config
cat > "$OUTPUT_FILE" << EOF
# go2rtc Configuration - AUTO-GENERATED from .env
# Regenerate: ./scripts/generate-go2rtc-config.sh

streams:
EOF

# Parse SKIP_CHANNELS into an array
IFS=',' read -ra SKIP_ARRAY <<< "$SKIP_CHANNELS"

for i in $(seq 1 "$NUM_CHANNELS"); do
    # Check if channel should be skipped
    skip=0
    for val in "${SKIP_ARRAY[@]}"; do
        # Strip whitespace from val just in case
        val=$(echo "$val" | xargs)
        if [[ "$val" == "$i" ]]; then
            skip=1
            break
        fi
    done

    if [[ $skip -eq 1 ]]; then
        log_info "Skipping channel $i (SKIP_CHANNELS)"
        continue
    fi

    echo "  cam${i}:" >> "$OUTPUT_FILE"
    echo "    - $(generate_url "$i")" >> "$OUTPUT_FILE"
    echo "    - \"ffmpeg:cam${i}#video=copy#audio=aac\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Mobile/Low-Bandwidth Stream (On-Demand Transcoding)
    # Uses VIDEO_CODEC, VIDEO_CRF, VIDEO_PRESET from .env
    CODEC="${VIDEO_CODEC:-libx264}"
    CRF="${VIDEO_CRF:-30}"
    PRESET="${VIDEO_PRESET:-superfast}"
    
    echo "  cam${i}_mobile:" >> "$OUTPUT_FILE"
    echo "    - \"ffmpeg:cam${i}#video=${CODEC}#width=854#raw=-tune zerolatency -preset ${PRESET} -crf ${CRF}\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
done

# Note: YouTube streaming is handled by youtube_restart.py, not go2rtc

# Add RTSP server section for relay functionality
cat >> "$OUTPUT_FILE" << EOF


rtsp:
  listen: ":${GO2RTC_RTSP_PORT}"

webrtc:
  listen: ":${GO2RTC_WEBRTC_PORT}"
  ice_servers:
    - urls: [stun:stun.l.google.com:19302]

api:
  listen: "127.0.0.1:${GO2RTC_API_PORT}"
  origin: "*"

log:
  level: info
EOF

log_info "Generated: $OUTPUT_FILE"
log_info "Channels: $NUM_CHANNELS | API: $GO2RTC_API_PORT | WebRTC: $GO2RTC_WEBRTC_PORT | RTSP: $GO2RTC_RTSP_PORT"
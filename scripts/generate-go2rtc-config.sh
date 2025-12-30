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
GO2RTC_API_PORT="${GO2RTC_API_PORT:-2127}"
GO2RTC_WEBRTC_PORT="${GO2RTC_WEBRTC_PORT:-8555}"
GO2RTC_RTSP_PORT="${GO2RTC_RTSP_PORT:-8554}"

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

for i in $(seq 1 "$NUM_CHANNELS"); do
    echo "  cam${i}: $(generate_url "$i")" >> "$OUTPUT_FILE"
done

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

# Add YouTube streams with audio transcoding for each configured stream key
# Stream key 1 -> cam1_youtube, Stream key 2 -> cam2_youtube, etc. up to 8
if [ "$YOUTUBE_LIVE_ENABLED" = "true" ]; then
    youtube_count=0
    
    # Check each stream key (1-8) and add corresponding YouTube stream
    for i in 1 2 3 4 5 6 7 8; do
        # Get stream key value using indirect reference
        key_var="YOUTUBE_STREAM_KEY_$i"
        key_value="${!key_var}"
        
        if [ -n "$key_value" ]; then
            sed -i "/^streams:/a\\  cam${i}_youtube: ffmpeg:cam${i}#video=copy#audio=aac" "$OUTPUT_FILE"
            log_info "Added cam${i}_youtube stream (with AAC audio for YouTube)"
            youtube_count=$((youtube_count + 1))
        fi
    done
    
    if [ $youtube_count -gt 0 ]; then
        log_info "YouTube streaming: ENABLED ($youtube_count channel(s))"
        log_info "Each stream restarts hourly to create separate YouTube videos"
    else
        log_warn "YouTube enabled but no stream keys configured (YOUTUBE_STREAM_KEY_1 to YOUTUBE_STREAM_KEY_8)"
    fi
fi

log_info "Generated: $OUTPUT_FILE"
log_info "Channels: $NUM_CHANNELS | API: $GO2RTC_API_PORT | WebRTC: $GO2RTC_WEBRTC_PORT | RTSP: $GO2RTC_RTSP_PORT"

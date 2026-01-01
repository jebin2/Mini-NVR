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
    echo "  cam${i}:" >> "$OUTPUT_FILE"
    echo "    - $(generate_url "$i")" >> "$OUTPUT_FILE"
    echo "    - \"ffmpeg:cam${i}#video=copy#audio=aac\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
done


# Add YouTube streams with audio transcoding for each configured stream key
# Stream key 1 -> cam1_youtube, Stream key 2 -> cam2_youtube, etc. up to 8
if [ "$YOUTUBE_LIVE_ENABLED" = "true" ]; then
    youtube_count=0
    
    # Check each stream key (1-8) and add corresponding YouTube stream
    # Check each stream key (1-8)
    grid_size="${YOUTUBE_GRID:-1}"
    
    for i in {1..8}; do
        # Get stream key value using indirect reference
        key_var="YOUTUBE_STREAM_KEY_$i"
        key_value="${!key_var}"
        
        if [ -n "$key_value" ]; then
            # Calculate range of cameras for this key
            start_cam=$(( (i - 1) * grid_size + 1 ))
            
            # Collect valid cameras for this grid
            valid_cams=()
            for (( j=0; j<grid_size; j++ )); do
                cam_num=$(( start_cam + j ))
                if [ "$cam_num" -le "$NUM_CHANNELS" ]; then
                    valid_cams+=("$cam_num")
                fi
            done
            
            count=${#valid_cams[@]}
            
            if [ "$count" -eq 1 ]; then
                # Single camera -> Direct to YouTube RTMP
                cam_num=${valid_cams[0]}
                rtmp_url="${YOUTUBE_RTMP_URL:-rtmp://a.rtmp.youtube.com/live2}"
                
                # FFmpeg command: cam -> H264 + silent AAC audio -> RTMP
                # YouTube requires audio, so we add silent audio track
                yt_cmd="exec:ffmpeg -hide_banner -loglevel error -rtsp_transport tcp -i rtsp://127.0.0.1:${GO2RTC_RTSP_PORT}/cam${cam_num} -f lavfi -i anullsrc=r=44100:cl=stereo -c:v libx264 -preset veryfast -tune zerolatency -b:v 2500k -maxrate 3000k -bufsize 6000k -r 25 -g 50 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest -f flv ${rtmp_url}/${key_value}"
                
                echo "  cam${i}_youtube:" >> "$OUTPUT_FILE"
                echo "    - \"$yt_cmd\"" >> "$OUTPUT_FILE"
                echo "" >> "$OUTPUT_FILE"
                
                log_info "Added cam${i}_youtube -> cam${cam_num} -> YouTube RTMP (with audio)"
                youtube_count=$((youtube_count + 1))
                
            elif [ "$count" -gt 1 ]; then
                # Grid Composition (2-4 cameras)
                # Optimized for YouTube Live Streaming with Lower Bitrate
                
                cmd="exec:ffmpeg -hide_banner -nostats -re"
                
                # Inputs from local go2rtc with TCP transport for stability
                filter_inputs=""
                
                # Add valid cameras as inputs with TCP transport
                for cam_num in "${valid_cams[@]}"; do
                    cmd="$cmd -rtsp_transport tcp -i rtsp://127.0.0.1:${GO2RTC_RTSP_PORT}/cam${cam_num}"
                done
                
                # Add black frames for missing slots to fill up to 4
                missing=$(( 4 - count ))
                for (( k=0; k<missing; k++ )); do
                    cmd="$cmd -f lavfi -i color=c=black:s=960x540:r=25"
                done
                
                # Construct video filter chain - LOWER RESOLUTION for bandwidth
                # Scale to 960x540 per camera (final output: 1920x1080)
                filter_complex=""
                for (( k=0; k<4; k++ )); do
                    filter_complex="${filter_complex}[${k}:v]scale=960x540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25[v${k}];"
                done
                
                # Build xstack from normalized inputs
                filter_complex="${filter_complex}"
                for (( k=0; k<4; k++ )); do
                    filter_complex="${filter_complex}[v${k}]"
                done
                filter_complex="${filter_complex}xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]"
                
                # NO AUDIO - Disabled for testing bandwidth issues
                audio_filter=""
                audio_map=""
                
                # Complete filter_complex
                full_filter="${filter_complex}${audio_filter}"
                
                # Encoding settings optimized for LOW BANDWIDTH YouTube Live
                cmd="$cmd -filter_complex \\\"${full_filter}\\\" -map \\\"[v]\\\" ${audio_map}"
                
                # NO AUDIO encoding
                cmd="$cmd -an"
                
                # Video encoding - AGGRESSIVE COMPRESSION for limited upload
                # Lower resolution (1920x1080), lower framerate (25fps), lower bitrate
                cmd="$cmd -c:v libx264 -preset faster -tune zerolatency"
                cmd="$cmd -b:v 2500k -minrate 2500k -maxrate 2500k -bufsize 5000k"
                cmd="$cmd -r 25 -g 50 -keyint_min 50 -sc_threshold 0 -pix_fmt yuv420p"
                
                # Output: mpegts to stdout for go2rtc consumption
                # YouTubeStreamer service handles pushing to YouTube RTMP via go2rtc API
                cmd="$cmd -f mpegts -"
                
                # Write to config file
                echo "  cam${i}_youtube:" >> "$OUTPUT_FILE"
                echo "    - \"$cmd\"" >> "$OUTPUT_FILE"
                
                log_info "Added cam${i}_youtube -> 2x2 Grid (Cams: ${valid_cams[*]}) with audio mixing"
                youtube_count=$((youtube_count + 1))
            fi
        fi
    done
    

    if [ $youtube_count -gt 0 ]; then
        log_info "YouTube streaming: ENABLED ($youtube_count channel(s))"
        log_info "Each stream restarts hourly to create separate YouTube videos"
    else
        log_warn "YouTube enabled but no stream keys configured (YOUTUBE_STREAM_KEY_1 to YOUTUBE_STREAM_KEY_8)"
    fi
fi

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
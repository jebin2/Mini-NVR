#!/bin/bash
# =============================================================================
# Mini-NVR Service Manager
# Starts and monitors all NVR services with automatic restart on failure.
# =============================================================================

MONITOR_LOG="/logs/monitor.log"
AUTH_FILE="need_auth.info"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$MONITOR_LOG"; }

# =============================================================================
# Hugging Face Storage Mount
# =============================================================================

HF_MOUNT_PID=""

mount_hf_bucket() {
    # Support both HF_BUCKET (preferred) and HF_REPO_ID (legacy)
    HF_BUCKET_ID="${HF_BUCKET:-$HF_REPO_ID}"
    
    if [ -z "$HF_BUCKET_ID" ]; then
        log "❌ HF_BUCKET not set! Cannot mount storage."
        exit 1
    fi
    if [ -z "$HF_TOKEN" ]; then
        log "❌ HF_TOKEN not set! Cannot authenticate with Hugging Face."
        exit 1
    fi
    
    log "Mounting Hugging Face bucket: $HF_BUCKET_ID to /recordings..."
    mkdir -p /recordings
    
    # Run hf-mount using NFS backend (needs nfs-common for mount.nfs)
    # NFS always uses advanced writes mode, perfect for ffmpeg
    HF_MOUNT_OUTPUT=$(hf-mount start --hf-token "$HF_TOKEN" bucket "$HF_BUCKET_ID" /recordings 2>&1)
    log "hf-mount output: $HF_MOUNT_OUTPUT"
    
    # Wait for NFS mount to become active (mountpoint detects real mounts)
    for i in $(seq 1 30); do
        if mountpoint -q /recordings 2>/dev/null; then
            log "✅ Hugging Face bucket successfully mounted!"
            return 0
        fi
        sleep 1
    done
    
    log "❌ Failed to mount Hugging Face bucket after 30 seconds!"
    exit 1
}

# Mount before anything else starts
mount_hf_bucket

# =============================================================================
# Service Definitions
# Each service has: command, enabled check, and optional special handling
# =============================================================================

declare -A SERVICE_CMD=(
    [server]="python server.py"
    [recorder]="python recorder.py"
    [cleanup]="python cleanup.py"
    [uploader]="python youtube_upload.py"
    [youtube_stream]="python youtube_stream.py"
)

# Order matters for startup
SERVICES=(server recorder cleanup uploader youtube_stream)

# Per-service "should run?" checks
is_enabled() {
    local name=$1
    case $name in
        uploader)        [ "${YOUTUBE_UPLOAD_ENABLED}" = "true" ] ;;
        youtube_stream)  [ "${YOUTUBE_LIVE_ENABLED}" = "true" ] ;;
        *)               true ;;  # Core services always enabled
    esac
}

# =============================================================================
# Service Management Functions
# =============================================================================

declare -A PIDS
declare -A START_TIMES

start_service() {
    local name=$1
    log "Starting $name: ${SERVICE_CMD[$name]}"
    setsid ${SERVICE_CMD[$name]} &
    PIDS[$name]=$!
    START_TIMES[$name]=$(date +%s)
}

stop_service() {
    local name=$1
    local pid=${PIDS[$name]}
    
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        log "Stopping $name (PID $pid)..."
        kill -TERM -$pid 2>/dev/null || kill -TERM $pid 2>/dev/null
        sleep 2
        kill -0 "$pid" 2>/dev/null && kill -KILL -$pid 2>/dev/null
        log "Stopped $name"
    fi
    PIDS[$name]=""
    START_TIMES[$name]=""
}

is_running() {
    local name=$1
    local pid=${PIDS[$name]}
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# =============================================================================
# Wait for go2rtc
# =============================================================================

GO2RTC_URL="http://127.0.0.1:${GO2RTC_API_PORT}/api"
log "Waiting for go2rtc..."

for i in $(seq 1 60); do
    python3 -c "import urllib.request; urllib.request.urlopen('$GO2RTC_URL', timeout=2)" 2>/dev/null && break
    [ $i -eq 60 ] && log "WARN: go2rtc not ready after 60s, starting anyway..."
    sleep 1
done
log "go2rtc ready"

# =============================================================================
# Startup
# =============================================================================

log "Starting services..."
for name in "${SERVICES[@]}"; do
    if is_enabled $name; then
        start_service $name
    else
        log "Skipping $name (disabled)"
    fi
done

# Graceful shutdown handler
cleanup() {
    log "Shutting down..."
    for name in "${SERVICES[@]}"; do
        stop_service $name
    done
    
    log "Unmounting Hugging Face bucket..."
    hf-mount stop /recordings 2>/dev/null || umount /recordings 2>/dev/null || true
    
    exit 0
}
trap cleanup SIGINT SIGTERM

# =============================================================================
# YouTube Stream Scheduled Restart Config
# =============================================================================

YT_RESTART_SECONDS=$(awk "BEGIN {printf \"%.0f\", ${YOUTUBE_LIVE_RESTART_INTERVAL_HOURS:-0} * 3600}")
YT_RESTART_DELAY="${YOUTUBE_LIVE_RESTART_DELAY_SECONDS:-0}"
[ "$YT_RESTART_SECONDS" -gt 0 ] && log "YouTube stream restart: every ${YOUTUBE_LIVE_RESTART_INTERVAL_HOURS}h, delay ${YT_RESTART_DELAY}s"

# =============================================================================
# Main Monitoring Loop
# =============================================================================

log "Monitoring services..."

while true; do
    current_time=$(date +%s)
    
    # --- Auth File Handling (only affects uploader, not youtube_stream) ---
    # youtube_stream uses stream keys (not OAuth), so it should keep running
    if [ -f "$AUTH_FILE" ]; then
        # Check if any OAuth-dependent service is enabled
        if is_enabled uploader; then
            log "🔐 Auth required. Pausing OAuth services (uploader)..."
            stop_service uploader
            
            if python3 trigger_auth.py; then
                log "✅ Auth success!"
                rm -f "$AUTH_FILE"
            else
                log "❌ Auth failed, retrying next loop..."
            fi
        else
            # No OAuth services enabled, just remove the auth file
            log "🔐 Auth file found but no OAuth services enabled. Removing..."
            rm -f "$AUTH_FILE"
        fi
        sleep 5
        continue
    fi
    
    # --- Service Health Check & Restart ---
    for name in "${SERVICES[@]}"; do
        # Skip if not enabled
        is_enabled $name || continue
        
        # Restart if died
        if ! is_running $name; then
            log "⚠ $name died, restarting in 10s..."
            sleep 10
            start_service $name
            log "Restarted $name (PID ${PIDS[$name]})"
        fi
        
        # YouTube stream scheduled restart
        if [ "$name" = "youtube_stream" ] && [ "$YT_RESTART_SECONDS" -gt 0 ]; then
            elapsed=$((current_time - ${START_TIMES[$name]:-0}))
            if [ "$elapsed" -ge "$YT_RESTART_SECONDS" ]; then
                log "🔄 Scheduled restart for youtube_stream (uptime: ${elapsed}s)"
                stop_service youtube_stream
                [ "$YT_RESTART_DELAY" -gt 0 ] && sleep "$YT_RESTART_DELAY"
                start_service youtube_stream
                log "✅ Restarted youtube_stream (PID ${PIDS[youtube_stream]})"
            fi
        fi
    done
    
    sleep 5
done

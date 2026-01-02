#!/bin/bash

# Log file for monitoring
MONITOR_LOG="/logs/monitor.log"

# Function to log messages with timestamp
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$MONITOR_LOG"
}

# Define services
NAMES=("server" "recorder" "cleanup" "uploader" "youtube_stream")
CMDS=("python server.py" "python recorder.py" "python cleanup.py" "python youtube_upload.py" "python youtube_stream.py")
PIDS=()
START_TIMES=()

# YouTube stream restart interval (in seconds)
# Converts YOUTUBE_LIVE_RESTART_INTERVAL_HOURS to seconds
YT_RESTART_HOURS="${YOUTUBE_LIVE_RESTART_INTERVAL_HOURS}"
YT_RESTART_DELAY="${YOUTUBE_LIVE_RESTART_DELAY_SECONDS}"

# Calculate seconds using awk (more reliable than bc)
YT_RESTART_SECONDS=$(awk "BEGIN {printf \"%.0f\", $YT_RESTART_HOURS * 3600}")

log_message "YouTube stream restart interval: ${YT_RESTART_HOURS}h (${YT_RESTART_SECONDS}s), delay: ${YT_RESTART_DELAY}s"

# Wait for go2rtc to be ready before starting services
GO2RTC_API_PORT="${GO2RTC_API_PORT:-2127}"
GO2RTC_API_URL="http://127.0.0.1:${GO2RTC_API_PORT}"

log_message "Waiting for go2rtc to be ready..."

wait_count=0
max_wait=60
while ! python3 -c "import urllib.request; urllib.request.urlopen('${GO2RTC_API_URL}/api', timeout=2)" > /dev/null 2>&1; do
    wait_count=$((wait_count + 1))
    if [ $wait_count -ge $max_wait ]; then
        log_message "ERROR: go2rtc not ready after ${max_wait}s. Starting anyway..."
        break
    fi
    sleep 1
done

if [ $wait_count -lt $max_wait ]; then
    log_message "go2rtc is ready after ${wait_count}s"
fi

log_message "Starting services..."

# Clean up any existing log file from previous run
if [ -n "$LOG_FILE" ]; then
    if [ -f "$LOG_FILE" ]; then
        log_message "Removing existing LOG_FILE: $LOG_FILE"
        rm -f "$LOG_FILE"
    fi
fi

# Function to stop a service (kills process group)
stop_service() {
    local index=$1
    local name=${NAMES[$index]}
    local pid=${PIDS[$index]}
    
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        log_message "Stopping $name service (PID $pid)..."
        # Kill the process group (negative PID = process group)
        kill -TERM -$pid 2>/dev/null || kill -TERM $pid 2>/dev/null
        sleep 2
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            log_message "Force killing $name..."
            kill -KILL -$pid 2>/dev/null || kill -KILL $pid 2>/dev/null
        fi
        log_message "Stopped $name service"
    fi
    PIDS[$index]=""
    START_TIMES[$index]=""
}

# Function to start a service
start_service() {
    local index=$1
    local name=${NAMES[$index]}
    local cmd=${CMDS[$index]}
    
    log_message "Starting $name service: $cmd"
    # Use setsid to create a new process group for the service
    setsid $cmd &
    PIDS[$index]=$!
    START_TIMES[$index]=$(date +%s)
}

# Start all services (conditionally based on env vars)
for i in "${!NAMES[@]}"; do
    name=${NAMES[$i]}

    if [ "$name" = "uploader" ] && [ "${YOUTUBE_UPLOAD_ENABLED}" != "true" ]; then
        log_message "Skipping $name service (YOUTUBE_UPLOAD_ENABLED != true)"
        PIDS[$i]=""
        continue
    fi

    if [ "$name" = "youtube_stream" ] && [ "${YOUTUBE_LIVE_ENABLED}" != "true" ]; then
        log_message "Skipping $name service (YOUTUBE_LIVE_ENABLED != true)"
        PIDS[$i]=""
        continue
    fi
    
    start_service $i
done

# Signal handler to kill all child processes on exit
cleanup() {
    log_message "Shutting down services..."
    for i in "${!NAMES[@]}"; do
        stop_service $i
    done
    exit 0
}

trap cleanup SIGINT SIGTERM

log_message "Monitoring services..."

# Get index of youtube_stream service
YT_INDEX=-1
for i in "${!NAMES[@]}"; do
    if [ "${NAMES[$i]}" = "youtube_stream" ]; then
        YT_INDEX=$i
        break
    fi
done

# Monitor loop
while true; do
    current_time=$(date +%s)
    
    for i in "${!NAMES[@]}"; do
        pid=${PIDS[$i]}
        name=${NAMES[$i]}
        start_time=${START_TIMES[$i]}
        
        # Check if service died
        if ! kill -0 "$pid" 2>/dev/null; then
            # If auth file exists, do not restart YouTube services
            if [ -f "need_auth.info" ] && { [ "$name" = "uploader" ] || [ "$name" = "youtube_stream" ]; }; then
                # Log only once per loop/state? To avoid spam, maybe nothing or debug
                # We already log "Pausing..." in the auth block below
                :
            else
                log_message "WARNING: Service $name (PID $pid) died. Restarting in 10s..."
                sleep 10
                start_service $i
                new_pid=${PIDS[$i]}
                log_message "Restarted $name with new PID $new_pid"
            fi
        fi
        
        # Special handling for youtube_stream: scheduled restart
        # Only if YOUTUBE_LIVE_RESTART_INTERVAL_HOURS is configured
        if [ "$i" = "$YT_INDEX" ] && [ -n "$start_time" ] && [ -n "$YT_RESTART_SECONDS" ] && [ "$YT_RESTART_SECONDS" -gt 0 ]; then
            elapsed=$((current_time - start_time))
            if [ "$elapsed" -ge "$YT_RESTART_SECONDS" ]; then
                log_message "🔄 Scheduled restart for youtube_stream (uptime: ${elapsed}s >= ${YT_RESTART_SECONDS}s)"
                stop_service $i
                if [ -n "$YT_RESTART_DELAY" ] && [ "$YT_RESTART_DELAY" -gt 0 ]; then
                    log_message "⏳ Waiting ${YT_RESTART_DELAY}s for YouTube to end previous stream..."
                    sleep "$YT_RESTART_DELAY"
                fi
                log_message "🚀 Starting new youtube_stream..."
                start_service $i
                new_pid=${PIDS[$i]}
                log_message "✅ Restarted youtube_stream with new PID $new_pid"
            fi
        fi
    done
    
    # Auth Handling
    # Check if auth is required (file created by uploader on failure)
    # The file is expected at app/need_auth.info (relative to project root?), but we are in /app so it is check ./need_auth.info
    AUTH_FILE="need_auth.info"
    
    if [ -f "$AUTH_FILE" ]; then
        log_message "🔐 Auth flag found ($AUTH_FILE). Pausing YouTube services..."
        
        # Stop YouTube services if running
        for i in "${!NAMES[@]}"; do
            name=${NAMES[$i]}
            if [ "$name" = "uploader" ] || [ "$name" = "youtube_stream" ]; then
                stop_service $i
            fi
        done
        
        log_message "Triggering SSH reauth..."
        if python3 trigger_auth.py; then
            log_message "✅ Auth trigger success! Removing flag and resuming..."
            rm -f "$AUTH_FILE"
        else
            log_message "❌ Auth trigger failed. Will retry next loop."
        fi
        
    else
        # Normal Operation: Ensure services are running
        # (The loop below restarts them if they are stopped and file doesn't exist)
        : # Do nothing here, let the restart logic handle it
    fi

    sleep 5
done

#!/bin/bash

# Log file for monitoring
MONITOR_LOG="/logs/monitor.log"

# Function to log messages with timestamp
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$MONITOR_LOG"
}

# Define services as an associative array (Service CMD -> Log Name)
# Note: integer keys are used for iteration in bash < 4 (which might be in some older dockers, but python:3.11-slim uses debian bookworm so newer bash is available)
# simpler approach: parallel arrays for robustness

NAMES=("server" "recorder" "cleanup" "uploader")
CMDS=("python server.py" "python recorder.py" "python cleanup.py" "python youtube_uploader/main.py")
PIDS=()

log_message "Starting services..."

# Clean up any existing log file from previous run if needed? 
# The user prompt had `if [ -n "$LOG_FILE" ]; then rm -f "$LOG_FILE"; fi` in the original CMD.
# I should preserve that logic if LOG_FILE is set.
if [ -n "$LOG_FILE" ]; then
    if [ -f "$LOG_FILE" ]; then
        log_message "Removing existing LOG_FILE: $LOG_FILE"
        rm -f "$LOG_FILE"
    fi
fi

# Function to start a service
start_service() {
    local index=$1
    local name=${NAMES[$index]}
    local cmd=${CMDS[$index]}
    
    log_message "Starting $name service: $cmd"
    $cmd &
    PIDS[$index]=$!
}

# Start all services
for i in "${!NAMES[@]}"; do
    start_service $i
done

# Signal handler to kill all child processes on exit
cleanup() {
    log_message "Shutting down services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
        fi
    done
    exit 0
}

trap cleanup SIGINT SIGTERM

log_message "Monitoring services..."

# Monitor loop
while true; do
    for i in "${!NAMES[@]}"; do
        pid=${PIDS[$i]}
        name=${NAMES[$i]}
        
        if ! kill -0 "$pid" 2>/dev/null; then
            log_message "WARNING: Service $name (PID $pid) died. Restarting..."
            start_service $i
            new_pid=${PIDS[$i]}
            log_message "Restarted $name with new PID $new_pid"
        fi
    done
    
    sleep 5
done

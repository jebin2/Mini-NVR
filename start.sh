#!/bin/bash
# Start Mini-NVR Docker stack
# Usage: ./start.sh [options]
#   -d  Run in background (detached)
#   -c  Clean logs and recordings before starting

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# Parse arguments
DETACHED=false
CLEAN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d) DETACHED=true; shift ;;
        -c) CLEAN=true; shift ;;
        -cd|-dc) DETACHED=true; CLEAN=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Function to stop YouTube uploader
stop_uploader() {
    if pgrep -f "youtube_uploader/main.py" > /dev/null 2>&1; then
        echo "Stopping YouTube Uploader..."
        pkill -f "youtube_uploader/main.py" 2>/dev/null || true
        sleep 1
        echo "YouTube Uploader stopped"
    fi
}

# Function to check if uploader is already running
is_uploader_running() {
    pgrep -f "youtube_uploader/main.py" > /dev/null 2>&1
}



echo "Stopping existing containers..."
docker compose down 2>/dev/null || true

# Also stop uploader when restarting
stop_uploader

# Clean logs and recordings if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning logs and recordings..."
    rm -rf ./logs/* 2>/dev/null || true
    rm -rf ./recordings/* 2>/dev/null || true
    echo "Cleaned: logs/, recordings/"
fi

# Export UID/GID for docker-compose to run container as current user
# This ensures files created in mounted volumes are owned by host user
export DOCKER_UID=$(id -u)
export DOCKER_GID=$(id -g)

# Create directories with correct ownership before Docker mounts them
mkdir -p ./logs ./recordings
touch ./logs/.keep ./recordings/.keep

echo "Generating go2rtc config..."
./scripts/generate-go2rtc-config.sh

echo "Generating web config..."
./scripts/generate-web-config.sh

echo "Building without cache..."
docker compose build --no-cache

# Function to start uploader if enabled and not already running
start_uploader_if_needed() {
    if grep -q "YOUTUBE_UPLOAD_ENABLED=true" .env 2>/dev/null; then
        if is_uploader_running; then
            echo "YouTube Uploader already running, skipping..."
        else
            if [ "$1" = "detached" ]; then
                echo "Starting YouTube Uploader (host, background)..."
                mkdir -p logs
                nohup python3 youtube_uploader/main.py > logs/youtube_uploader.log 2>&1 &
                echo "YouTube Uploader PID: $!"
                echo "View logs: tail -f logs/youtube_uploader.log"
            else
                echo "Starting YouTube Uploader (host, background)..."
                python3 youtube_uploader/main.py &
                UPLOADER_PID=$!
                echo "YouTube Uploader PID: $UPLOADER_PID"
                # Cleanup uploader when docker compose exits
                trap "kill $UPLOADER_PID 2>/dev/null" EXIT
            fi
        fi
    fi
}

if [ "$DETACHED" = true ]; then
    echo "Starting containers (background)..."
    docker compose up -d
    echo "Running in background. View logs: docker compose logs -f"
    start_uploader_if_needed "detached"
else
    echo "Starting containers (foreground)..."
    start_uploader_if_needed "foreground"
    docker compose up
fi

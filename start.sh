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

# duplicate service won't run
echo "Stopping any running instances..."
./stop.sh

echo "Removing existing containers..."
docker compose down 2>/dev/null || true

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
mkdir -p ./logs ./recordings ./encrypt

echo "Generating go2rtc config..."
./scripts/generate-go2rtc-config.sh

echo "Generating web config..."
./scripts/generate-web-config.sh

echo "Building without cache..."
docker compose build --no-cache

# YouTube Uploader now runs INSIDE Docker container
# Auth is triggered via SSH when needed (see scripts/reauth.py)
# For manual auth: python3 scripts/reauth.py

if [ "$DETACHED" = true ]; then
    echo "Starting containers (background)..."
    docker compose up -d
    echo "Running in background."
    echo ""
    echo "View logs: docker compose logs -f"
    echo "View uploader: docker logs mini-nvr 2>&1 | grep 'NVR Uploader'"
else
    echo "Starting containers (foreground)..."
    docker compose up
fi


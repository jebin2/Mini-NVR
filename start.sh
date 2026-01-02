#!/bin/bash
# Start Mini-NVR Docker stack
# Usage: ./start.sh [options]
#   -d  Run in background (detached)
#   -c  Clean logs and encrypt before starting (excluding recordings)
#   -r  Clean recordings before starting
#   -b  Force rebuild Docker image without cache

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# Parse arguments
DETACHED=false
CLEAN=false
CLEAN_RECORDINGS=false
BUILD_NO_CACHE=false

while [[ $# -gt 0 ]]; do
    if [[ "$1" == -* ]]; then
        # Iterate over each character in the argument (skip the first '-')
        for (( i=1; i<${#1}; i++ )); do
            char="${1:$i:1}"
            case "$char" in
                d) DETACHED=true ;;
                c) CLEAN=true ;;
                r) CLEAN_RECORDINGS=true ;;
                b) BUILD_NO_CACHE=true ;;
                *) echo "Unknown option: -$char"; exit 1 ;;
            esac
        done
    else
        echo "Unknown argument: $1"
        exit 1
    fi
    shift
done

# duplicate service won't run
echo "Stopping any running instances..."
./stop.sh

echo "Removing existing containers..."
docker compose down 2>/dev/null || true

# Clean logs and encrypt if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning logs and encrypt..."
    sudo rm -rf ./logs/* 2>/dev/null || true
    sudo rm -rf ./encrypt/* 2>/dev/null || true
    echo "Cleaned: logs/, encrypt/"
fi

# Clean recordings only if requested
if [ "$CLEAN_RECORDINGS" = true ]; then
    echo "Cleaning recordings..."
    sudo rm -rf ./recordings/* 2>/dev/null || true
    echo "Cleaned: recordings/"
fi

# Docker cleanup when building or cleaning (removes dangling images, build cache)
if [ "$CLEAN" = true ] || [ "$BUILD_NO_CACHE" = true ]; then
    echo "Cleaning up Docker resources (dangling images, build cache)..."
    docker system prune -f >/dev/null 2>&1 || true
    echo "Docker cleanup complete."
fi

# Export UID/GID for docker-compose to run container as current user
# This ensures files created in mounted volumes are owned by host user
export DOCKER_UID=$(id -u)
export DOCKER_GID=$(id -g)

# Create directories with correct ownership before Docker mounts them
mkdir -p ./logs ./recordings ./encrypt

# Fix ownership if directories are owned by root (from Docker running as root)
for dir in ./logs ./recordings ./encrypt; do
    if [ -d "$dir" ] && [ "$(stat -c '%u' $dir 2>/dev/null)" = "0" ]; then
        echo "Fixing $dir directory ownership..."
        sudo chown -R $(id -u):$(id -g) "$dir"
    fi
done

echo "Generating go2rtc config..."
./scripts/generate-go2rtc-config.sh

echo "Generating web config..."
./scripts/generate-web-config.sh

# Build Docker image
if [ "$BUILD_NO_CACHE" = true ]; then
    echo "Building without cache (force rebuild)..."
    docker compose build --no-cache
else
    echo "Building Docker image..."
    docker compose build
fi

# YouTube Uploader now runs INSIDE Docker container
# Auth is triggered via SSH when needed (see youtube_authenticate/reauth.py)
# For manual auth: python3 youtube_authenticate/reauth.py

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

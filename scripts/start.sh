#!/bin/bash
# Start Mini-NVR Docker stack
# Usage: ./scripts/start.sh [options]
#   -d  Run in background (detached)
#   -c  Clean logs and recordings before starting

set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."

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

echo "Stopping existing containers..."
docker compose down 2>/dev/null || true

# Clean logs and recordings if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning logs and recordings..."
    rm -rf ./logs/* 2>/dev/null || true
    rm -rf ./recordings/* 2>/dev/null || true
    echo "Cleaned: logs/, recordings/"
fi

echo "Generating go2rtc config..."
./scripts/generate-go2rtc-config.sh

echo "Generating web config..."
./scripts/generate-web-config.sh

echo "Building without cache..."
docker compose build --no-cache

if [ "$DETACHED" = true ]; then
    echo "Starting containers (background)..."
    docker compose up -d
    echo "Running in background. View logs: docker compose logs -f"
else
    echo "Starting containers (foreground)..."
    docker compose up
fi

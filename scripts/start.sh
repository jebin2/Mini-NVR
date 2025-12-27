#!/bin/bash
# Start Mini-NVR Docker stack
# Usage: ./scripts/start.sh [-d]
#   -d  Run in background (detached)

set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Stopping existing containers..."
docker compose down 2>/dev/null || true

echo "Generating go2rtc config..."
./scripts/generate-go2rtc-config.sh

echo "Generating web config..."
./scripts/generate-web-config.sh

echo "Building without cache..."
docker compose build --no-cache

if [ "$1" = "-d" ]; then
    echo "Starting containers (background)..."
    docker compose up -d
    echo "Running in background. View logs: docker compose logs -f"
else
    echo "Starting containers (foreground)..."
    docker compose up
fi

#!/bin/bash
# ============================================
# Mini-NVR Start Script
# Usage: ./start.sh [options]
#   -d  Run in background (detached)
#   -c  Clean logs and encrypt before starting
#   -r  Clean recordings before starting
#   -b  Force rebuild Docker image without cache
# ============================================

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# ============================================
# GLOBAL VARIABLES
# ============================================
DETACHED=false
CLEAN=false
CLEAN_RECORDINGS=false
BUILD_NO_CACHE=false

# ============================================
# UTILITY FUNCTIONS
# ============================================
log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }

# ============================================
# CORE FUNCTIONS
# ============================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == -* ]]; then
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
}

stop_existing() {
    log_info "Stopping any running instances..."
    ./stop.sh

    log_info "Removing existing containers..."
    docker compose down 2>/dev/null || true
}

clean_data() {
    if [ "$CLEAN" = true ]; then
        log_info "Cleaning logs and encrypt..."
        sudo rm -rf ./logs/* 2>/dev/null || true
        sudo rm -rf ./encrypt/* 2>/dev/null || true
        echo "Cleaned: logs/, encrypt/"
    fi

    if [ "$CLEAN_RECORDINGS" = true ]; then
        log_info "Cleaning recordings..."
        sudo rm -rf ./recordings/* 2>/dev/null || true
        echo "Cleaned: recordings/"
    fi

    # Docker cleanup when building or cleaning
    if [ "$CLEAN" = true ] || [ "$BUILD_NO_CACHE" = true ]; then
        log_info "Cleaning Docker resources..."
        docker system prune -f >/dev/null 2>&1 || true
        echo "Docker cleanup complete."
    fi
}

setup_directories() {
    # Export UID/GID for docker-compose
    export DOCKER_UID=$(id -u)
    export DOCKER_GID=$(id -g)

    # Create directories
    mkdir -p ./logs ./recordings ./encrypt

    # Fix ownership if owned by root
    for dir in ./logs ./recordings ./encrypt; do
        if [ -d "$dir" ] && [ "$(stat -c '%u' $dir 2>/dev/null)" = "0" ]; then
            log_info "Fixing $dir ownership..."
            sudo chown -R $(id -u):$(id -g) "$dir"
        fi
    done
}

generate_configs() {
    log_info "Generating go2rtc config..."
    ./scripts/generate-go2rtc-config.sh
}

build_docker() {
    if [ "$BUILD_NO_CACHE" = true ]; then
        log_info "Building without cache (force rebuild)..."
        docker compose build --no-cache
    else
        log_info "Building Docker image..."
        docker compose build
    fi
}

start_containers() {
    if [ "$DETACHED" = true ]; then
        log_info "Starting containers (background)..."
        docker compose up -d
        echo "Running in background."
        echo ""
        echo "View logs: docker compose logs -f"
        echo "View uploader: docker logs mini-nvr 2>&1 | grep 'NVR Uploader'"
    else
        log_info "Starting containers (foreground)..."
        docker compose up
    fi
}

# ============================================
# MAIN
# ============================================
main() {
    # Parse command line arguments
    parse_arguments "$@"

    # Step 1: Stop existing containers
    stop_existing

    # Step 2: Clean data if requested
    clean_data

    # Step 3: Setup directories and permissions
    setup_directories

    # Step 4: Generate configs
    generate_configs

    # Step 5: Build Docker image
    build_docker

    # Step 6: Start containers
    start_containers
}

# Run main with all arguments
main "$@"

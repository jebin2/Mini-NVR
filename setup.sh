#!/bin/bash
# ============================================
# Mini-NVR Setup Script
# Usage: source setup.sh
# ============================================

# Ensure script is sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "❌ Please run: source setup.sh"
    exit 1
fi

# ============================================
# GLOBAL VARIABLES
# ============================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DIR_NAME=$(basename "$(pwd)")
ENV_NAME="${DIR_NAME}_env"
YOUTUBE_NEEDED=false

# ============================================
# UTILITY FUNCTIONS
# ============================================
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================
# SETUP FUNCTIONS
# ============================================

detect_youtube_features() {
    log_info "Detecting YouTube feature configuration..."
    
    if [ -f ".env" ]; then
        local yt_live=$(grep "^YOUTUBE_LIVE_ENABLED=" .env 2>/dev/null | cut -d '=' -f2 | tr -d '"' | tr -d "'" | tr '[:upper:]' '[:lower:]')
        local yt_upload=$(grep "^YOUTUBE_UPLOAD_ENABLED=" .env 2>/dev/null | cut -d '=' -f2 | tr -d '"' | tr -d "'" | tr '[:upper:]' '[:lower:]')
        
        if [ "$yt_live" = "true" ] || [ "$yt_upload" = "true" ]; then
            YOUTUBE_NEEDED=true
            log_info "YouTube features: ENABLED"
        else
            log_info "YouTube features: DISABLED"
        fi
    else
        log_warn ".env not found - assuming YouTube features disabled"
    fi
}

setup_pyenv() {
    if [ "$YOUTUBE_NEEDED" != "true" ]; then
        log_info "Skipping pyenv setup (YouTube features disabled)"
        return 0
    fi

    log_info "Setting up pyenv environment: $ENV_NAME"

    # Check if pyenv is available
    if ! command -v pyenv &> /dev/null; then
        log_warn "pyenv is not installed - YouTube features will be disabled"
        YOUTUBE_NEEDED=false
        return 0
    fi

    # Check if penv function exists
    if ! declare -F penv &>/dev/null; then
        log_warn "'penv' command not found - YouTube features will be disabled"
        YOUTUBE_NEEDED=false
        return 0
    fi

    # Activate environment
    penv
    if [ $? -ne 0 ]; then
        log_warn "Failed to activate pyenv - YouTube features will be disabled"
        YOUTUBE_NEEDED=false
        return 0
    fi

    log_info "pyenv environment activated"
}

build_frontend() {
    log_info "Building React Frontend..."

    # Get Google Client ID from .env
    local g_client_id=""
    if [ -f ".env" ]; then
        g_client_id=$(grep "^GOOGLE_CLIENT_ID=" .env | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    fi

    if [ -z "$g_client_id" ]; then
        log_warn "GOOGLE_CLIENT_ID not found in .env. Frontend google auth may not work."
    fi

    # Build web-react
    if [ ! -d "web-react" ]; then
        log_warn "web-react directory not found. Skipping frontend build."
        return 0
    fi

    pushd web-react > /dev/null

    log_info "Clean install: removing node_modules and lockfile..."
    rm -rf node_modules package-lock.json

    log_info "Installing frontend dependencies..."
    npm install

    log_info "Building frontend..."
    VITE_GOOGLE_CLIENT_ID="$g_client_id" VITE_API_BASE_URL="/api" npm run build

    if [ $? -eq 0 ]; then
        log_info "Frontend build successful."
        popd > /dev/null

        # Deploy to web/
        if [ -d "web-react/dist" ]; then
            log_info "Deploying new frontend to web/..."
            rm -rf web 2>/dev/null
            mv web-react/dist web
            log_info "Deployment complete."
        else
            log_error "web-react/dist not found after build."
        fi
    else
        log_error "Frontend build failed."
        popd > /dev/null
        return 1
    fi
}

install_python_deps() {
    log_info "Installing Python requirements..."
    pip install --force-reinstall -r requirements.txt
}

check_system_deps() {
    log_info "Checking system dependencies..."

    # Check ffmpeg
    if command -v ffmpeg &> /dev/null; then
        log_info "ffmpeg: ✓ installed"
    else
        log_warn "ffmpeg: ✗ not installed"
        if [ -f /etc/debian_version ]; then
            read -p "Install ffmpeg via apt? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo apt-get update && sudo apt-get install -y ffmpeg
            fi
        else
            log_warn "Please install ffmpeg manually."
        fi
    fi

    # Check cloudflared
    if command -v cloudflared &> /dev/null; then
        log_info "cloudflared: ✓ installed"
    else
        log_warn "cloudflared: ✗ not installed (needed for Cloudflare Tunnel)"
        if [ -f /etc/debian_version ]; then
            read -p "Install cloudflared? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "Installing cloudflared..."
                curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
                echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
                sudo apt-get update && sudo apt-get install -y cloudflared
                log_info "cloudflared installed."
            fi
        else
            log_warn "Please install cloudflared manually."
        fi
    fi
}

validate_config() {
    log_info "Validating configuration..."

    # Create .env if missing
    if [ ! -f ".env" ]; then
        log_warn ".env file not found!"
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_info "Created .env from .env.example. Please edit it."
        fi
        return 0
    fi

    # Check for missing keys
    if [ -f ".env.example" ]; then
        local missing=0
        while IFS='=' read -r key value || [ -n "$key" ]; do
            [[ $key =~ ^#.* ]] && continue
            [[ -z $key ]] && continue
            if ! grep -q "^$key=" .env; then
                log_warn "Missing key: $key"
                missing=$((missing+1))
            fi
        done < .env.example

        if [ $missing -eq 0 ]; then
            log_info "All configuration keys present."
        else
            log_warn "Found $missing missing keys in .env"
        fi
    fi

    # Check JWT_SECRET
    local jwt=$(grep "^JWT_SECRET=" .env | cut -d '=' -f2)
    if [ -z "$jwt" ]; then
        log_error "JWT_SECRET is missing or empty!"
        echo "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        return 1
    fi
}

setup_ssh_auth() {
    if [ "$YOUTUBE_NEEDED" != "true" ]; then
        log_info "Skipping SSH auth setup (YouTube features disabled)"
        return 0
    fi

    echo ""
    log_info "Setting up SSH for Docker-to-host auth..."
    
    if [ -f "scripts/setup-ssh-auth.sh" ]; then
        bash scripts/setup-ssh-auth.sh
    else
        log_error "SSH auth script not found: scripts/setup-ssh-auth.sh"
    fi
}

setup_cloudflare_tunnel() {
    echo ""
    read -p "Set up Cloudflare Tunnel for remote access? (y/n) " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Skipped Cloudflare Tunnel setup."
        log_info "Run later with: ./scripts/setup_cloudflare_tunnel.sh"
        return 0
    fi

    if ! command -v cloudflared &> /dev/null; then
        log_error "cloudflared not installed. Run setup.sh again to install."
        return 1
    fi

    if [ -f "scripts/setup_cloudflare_tunnel.sh" ]; then
        bash scripts/setup_cloudflare_tunnel.sh
    else
        log_error "Tunnel script not found: scripts/setup_cloudflare_tunnel.sh"
    fi
}

# ============================================
# MAIN
# ============================================
main() {
    echo ""
    echo "============================================"
    echo "         Mini-NVR Setup"
    echo "============================================"
    echo ""

    # Step 1: Detect YouTube features
    detect_youtube_features

    # Step 2: Setup pyenv (if YouTube enabled)
    setup_pyenv

    # Step 3: Build frontend
    build_frontend

    # Step 4: Install Python dependencies
    install_python_deps

    # Step 5: Check system dependencies
    check_system_deps

    # Step 6: Validate configuration
    validate_config || return 1

    # Step 7: SSH auth (if YouTube enabled)
    setup_ssh_auth

    # Step 8: Cloudflare tunnel (optional)
    setup_cloudflare_tunnel

    echo ""
    log_info "============================================"
    log_info "  Setup complete! Environment: $ENV_NAME"
    log_info "============================================"
}

# Run main
main

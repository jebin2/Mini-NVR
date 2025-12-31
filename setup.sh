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

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 1. Environment Setup (Mimicking penv logic)
# Get folder name as env name suffix
DIR_NAME=$(basename "$(pwd)")
ENV_NAME="${DIR_NAME}_env"
REQUIRED_PYTHON="3.10" # Min version, adjust as needed

log_info "Setting up environment: $ENV_NAME"

if ! command -v pyenv &> /dev/null; then
    log_error "pyenv is not installed or not in PATH. Please install pyenv."
    return 1 2>/dev/null || exit 1
fi

# penv FUNCTION check (important)
if ! declare -F penv &>/dev/null; then
    log_error "'penv' command not found."
    return 1
fi

# Activate
penv
if [ $? -ne 0 ]; then
    log_error "Failed to activate environment."
    return 1 2>/dev/null || exit 1
fi

# 2. Dependencies
log_info "Installing requirements..."
if [ -f "requirements.txt" ]; then
    pip install --force-reinstall -r requirements.txt
else
    log_warn "requirements.txt not found."
fi

if [ -f "youtube_uploader/requirements.txt" ]; then
    log_info "Installing youtube_uploader requirements..."
    pip install --force-reinstall -r youtube_uploader/requirements.txt
else
    log_warn "youtube_uploader/requirements.txt not found."
fi

# 3. System Dependencies
log_info "Checking system dependencies..."

# Check ffmpeg
if command -v ffmpeg &> /dev/null; then
    log_info "ffmpeg is installed."
else
    log_warn "ffmpeg is NOT installed."
    if [ -f /etc/debian_version ]; then
        read -p "Do you want to try installing ffmpeg via apt? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
        else
            log_warn "Skipping ffmpeg installation. Some features may not work."
        fi
    else
        log_warn "Please install ffmpeg manually."
    fi
fi

# Check cloudflared (for Cloudflare Tunnel)
if command -v cloudflared &> /dev/null; then
    log_info "cloudflared is installed."
else
    log_warn "cloudflared is NOT installed (needed for Cloudflare Tunnel)."
    if [ -f /etc/debian_version ]; then
        read -p "Do you want to install cloudflared? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Installing cloudflared..."
            curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
            echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
            sudo apt-get update && sudo apt-get install -y cloudflared
            log_info "cloudflared installed successfully."
        else
            log_warn "Skipping cloudflared installation. Run scripts/setup_cloudflare_tunnel.sh later."
        fi
    else
        log_warn "Please install cloudflared manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    fi
fi

# 4. Configuration Check
log_info "Checking configuration..."
if [ ! -f ".env" ]; then
    log_warn ".env file not found!"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_info "Created .env from .env.example. Please edit it with your settings."
    fi
fi

if [ -f ".env" ] && [ -f ".env.example" ]; then
    # Simple key check
    MISSING_KEYS=0
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # Skip comments and empty lines
        [[ $key =~ ^#.* ]] && continue
        [[ -z $key ]] && continue
        
        # Check if key exists in .env
        if ! grep -q "^$key=" .env; then
            log_warn "Missing key in .env: $key"
            MISSING_KEYS=$((MISSING_KEYS+1))
        fi
    done < .env.example
    
    if [ $MISSING_KEYS -eq 0 ]; then
        log_info "Configuration check passed (keys exist)."
    else
        log_warn "Found $MISSING_KEYS missing configuration keys in .env."
    fi
fi

# 5. SSH Auth Setup for Docker (Required for YouTube uploader)
echo ""
log_info "Setting up SSH for Docker-to-host auth triggering..."
if [ -f "scripts/setup-ssh-auth.sh" ]; then
    bash scripts/setup-ssh-auth.sh
else
    log_error "SSH auth setup script not found: scripts/setup-ssh-auth.sh"
fi

# 6. Cloudflare Tunnel Setup (Optional)
echo ""
read -p "Do you want to set up Cloudflare Tunnel for remote access? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v cloudflared &> /dev/null; then
        if [ -f "scripts/setup_cloudflare_tunnel.sh" ]; then
            bash scripts/setup_cloudflare_tunnel.sh
        else
            log_error "Cloudflare tunnel script not found: scripts/setup_cloudflare_tunnel.sh"
        fi
    else
        log_error "cloudflared is not installed. Please run setup.sh again and install it first."
    fi
else
    log_info "Skipped Cloudflare Tunnel setup."
    log_info "You can set it up later with: ./scripts/setup_cloudflare_tunnel.sh"
fi

log_info "Setup complete! Environment '$ENV_NAME' is active."

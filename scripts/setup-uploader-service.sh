#!/bin/bash
# Setup/Remove Mini-NVR YouTube Uploader systemd service
# Usage: 
#   ./scripts/setup-uploader-service.sh install  - Install and enable the service
#   ./scripts/setup-uploader-service.sh remove   - Stop and remove the service
#   ./scripts/setup-uploader-service.sh status   - Check service status

set -e

SERVICE_NAME="mini-nvr-uploader"
SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_FILE="$PROJECT_DIR/scripts/mini-nvr-uploader.service"
SYSTEMD_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

install_service() {
    echo "Installing $SERVICE_NAME service..."
    
    # Auto-detect current user and paths
    CURRENT_USER=$(whoami)
    ENV_NAME="Mini-NVR_env"
    LOG_FILE="$PROJECT_DIR/logs/youtube_uploader.log"
    ENV_FILE="$PROJECT_DIR/.env"
    
    # Detect Python path - check pyenv first, then local venv
    PYTHON_PATH=""
    
    # Check pyenv virtualenv location
    PYENV_PYTHON="$HOME/.pyenv/versions/$ENV_NAME/bin/python"
    if [ -f "$PYENV_PYTHON" ]; then
        PYTHON_PATH="$PYENV_PYTHON"
        print_status "Found pyenv environment: $PYTHON_PATH"
    fi
    
    # Check local venv in project directory
    LOCAL_PYTHON="$PROJECT_DIR/$ENV_NAME/bin/python"
    if [ -z "$PYTHON_PATH" ] && [ -f "$LOCAL_PYTHON" ]; then
        PYTHON_PATH="$LOCAL_PYTHON"
        print_status "Found local venv: $PYTHON_PATH"
    fi
    
    # Verify python was found
    if [ -z "$PYTHON_PATH" ]; then
        print_error "Virtual environment '$ENV_NAME' not found."
        print_error "Checked locations:"
        print_error "  - pyenv: $PYENV_PYTHON"
        print_error "  - local: $LOCAL_PYTHON"
        print_error "Please run 'source setup.sh' first to create the environment."
        exit 1
    fi
    
    # Create logs directory if needed
    mkdir -p "$PROJECT_DIR/logs"
    
    # Stop existing service if running
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        print_warning "Stopping existing service..."
        sudo systemctl stop "$SERVICE_NAME"
    fi
    
    # Generate service file dynamically with correct user and paths
    print_status "Generating service file for user: $CURRENT_USER"
    cat > /tmp/$SERVICE_NAME.service << EOF
[Unit]
Description=Mini-NVR YouTube Uploader
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH youtube_uploader/main.py
Restart=always
RestartSec=10
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

# Environment file (optional, loads .env)
EnvironmentFile=-$ENV_FILE

[Install]
WantedBy=multi-user.target
EOF
    
    # Copy generated service file
    sudo cp /tmp/$SERVICE_NAME.service "$SYSTEMD_DIR/"
    rm /tmp/$SERVICE_NAME.service
    print_status "Service file installed to $SYSTEMD_DIR"
    
    # Reload systemd
    sudo systemctl daemon-reload
    print_status "Systemd reloaded"
    
    # Enable service (auto-start on boot)
    sudo systemctl enable "$SERVICE_NAME"
    print_status "Service enabled (auto-start on boot)"
    
    # Start service
    sudo systemctl start "$SERVICE_NAME"
    print_status "Service started"
    
    echo ""
    echo "Installation complete! Service status:"
    sudo systemctl status "$SERVICE_NAME" --no-pager
}

remove_service() {
    echo "Removing $SERVICE_NAME service..."
    
    # Stop service if running
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        sudo systemctl stop "$SERVICE_NAME"
        print_status "Service stopped"
    fi
    
    # Disable service
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        sudo systemctl disable "$SERVICE_NAME"
        print_status "Service disabled"
    fi
    
    # Remove service file
    if [ -f "$SYSTEMD_DIR/$SERVICE_NAME.service" ]; then
        sudo rm "$SYSTEMD_DIR/$SERVICE_NAME.service"
        print_status "Service file removed"
    fi
    
    # Reload systemd
    sudo systemctl daemon-reload
    print_status "Systemd reloaded"
    
    echo ""
    print_status "Service removed successfully"
}

show_status() {
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo "Service is RUNNING"
        sudo systemctl status "$SERVICE_NAME" --no-pager
    elif [ -f "$SYSTEMD_DIR/$SERVICE_NAME.service" ]; then
        echo "Service is INSTALLED but NOT RUNNING"
        sudo systemctl status "$SERVICE_NAME" --no-pager || true
    else
        echo "Service is NOT INSTALLED"
    fi
}

# Main
case "${1:-}" in
    install)
        install_service
        ;;
    remove)
        remove_service
        ;;
    status)
        show_status
        ;;
    *)
        echo "Mini-NVR YouTube Uploader Service Manager"
        echo ""
        echo "Usage: $0 {install|remove|status}"
        echo ""
        echo "  install  - Install and enable the service (auto-start on boot)"
        echo "  remove   - Stop and remove the service completely"
        echo "  status   - Check if service is running"
        exit 1
        ;;
esac

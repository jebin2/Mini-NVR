#!/bin/bash
# Setup SSH for Docker-to-Host authentication triggering
# This script is IDEMPOTENT - safe to run multiple times
#
# Usage: ./scripts/setup-ssh-auth.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

echo "========================================"
echo "SSH Setup for Docker-to-Host Auth"
echo "========================================"
echo ""

# 1. Check if SSH server is installed and running
echo "Checking SSH server..."
if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
    print_status "SSH server is running"
else
    print_warning "SSH server not running. Attempting to start..."
    
    # Try to install if not present
    if ! command -v sshd &> /dev/null; then
        print_warning "Installing openssh-server..."
        sudo apt-get update && sudo apt-get install -y openssh-server
    fi
    
    # Enable and start
    sudo systemctl enable ssh 2>/dev/null || sudo systemctl enable sshd 2>/dev/null || true
    sudo systemctl start ssh 2>/dev/null || sudo systemctl start sshd 2>/dev/null
    
    if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
        print_status "SSH server started successfully"
    else
        print_error "Failed to start SSH server. Please install manually."
        exit 1
    fi
fi

# 2. Check/Generate SSH key pair
SSH_KEY="$HOME/.ssh/id_rsa"
echo ""
echo "Checking SSH keys..."

if [ -f "$SSH_KEY" ]; then
    print_status "SSH key already exists: $SSH_KEY"
else
    print_warning "No SSH key found. Generating..."
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    ssh-keygen -t rsa -b 4096 -N "" -f "$SSH_KEY"
    print_status "SSH key generated: $SSH_KEY"
fi

# 3. Add public key to authorized_keys (if not already present)
echo ""
echo "Checking authorized_keys..."
AUTH_KEYS="$HOME/.ssh/authorized_keys"
PUB_KEY=$(cat "$SSH_KEY.pub")

if [ -f "$AUTH_KEYS" ] && grep -qF "$PUB_KEY" "$AUTH_KEYS" 2>/dev/null; then
    print_status "Public key already in authorized_keys"
else
    print_warning "Adding public key to authorized_keys..."
    echo "$PUB_KEY" >> "$AUTH_KEYS"
    chmod 600 "$AUTH_KEYS"
    print_status "Public key added to authorized_keys"
fi

# 4. Add localhost/host.docker.internal to known_hosts
echo ""
echo "Checking known_hosts..."
KNOWN_HOSTS="$HOME/.ssh/known_hosts"

# Get host keys
add_to_known_hosts() {
    local host=$1
    if ! grep -q "^$host " "$KNOWN_HOSTS" 2>/dev/null; then
        print_warning "Adding $host to known_hosts..."
        ssh-keyscan -H "$host" >> "$KNOWN_HOSTS" 2>/dev/null || true
    else
        print_status "$host already in known_hosts"
    fi
}

# Ensure file exists
touch "$KNOWN_HOSTS"
chmod 644 "$KNOWN_HOSTS"

add_to_known_hosts "localhost"
add_to_known_hosts "127.0.0.1"

# For Docker's host.docker.internal, use the host's actual IP
# This gets resolved inside Docker, but we need the actual IP for known_hosts
HOST_IP=$(hostname -I | awk '{print $1}')
if [ -n "$HOST_IP" ]; then
    add_to_known_hosts "$HOST_IP"
    print_status "Added host IP ($HOST_IP) to known_hosts"
fi

# 5. Test SSH connection
echo ""
echo "Testing SSH connection to localhost..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 localhost echo "SSH connection successful" 2>/dev/null; then
    print_status "SSH to localhost works"
else
    print_error "SSH to localhost failed. Please check SSH configuration."
    print_warning "Try: ssh localhost"
    exit 1
fi

# 6. Test with same pattern Docker will use
echo ""
echo "Testing SSH pattern Docker will use..."
CURRENT_USER=$(whoami)
if ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 "${CURRENT_USER}@localhost" echo "Docker-style SSH works" 2>/dev/null; then
    print_status "Docker-style SSH (${CURRENT_USER}@localhost) works"
else
    print_warning "Docker-style SSH may have issues. Will try with host IP..."
fi

echo ""
echo "========================================"
print_status "SSH setup complete!"
echo "========================================"
echo ""
echo "Summary:"
echo "  SSH Key:     $SSH_KEY"
echo "  Auth Keys:   $AUTH_KEYS"
echo "  Known Hosts: $KNOWN_HOSTS"
echo "  Host User:   $CURRENT_USER"
echo "  Host IP:     ${HOST_IP:-unknown}"
echo ""
echo "Docker will use: ssh ${CURRENT_USER}@host.docker.internal <command>"
echo ""
print_status "You can now run: ./start.sh"

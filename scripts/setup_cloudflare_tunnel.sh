#!/usr/bin/env bash
set -e

# ========= Load from .env =========
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ .env file not found at $ENV_FILE"
  echo "   Please run 'source setup.sh' first to create it."
  exit 1
fi

# Source .env to get variables
set -a
source "$ENV_FILE"
set +a

# Config from .env (with defaults)
TUNNEL_NAME="${CF_TUNNEL_NAME:-cctv}"
DOMAIN="${CF_TUNNEL_DOMAIN:-}"
LOCAL_PORT_UI="${WEB_PORT:-}"
CLOUDFLARED_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CLOUDFLARED_DIR/config.yml"

if [ -z "$DOMAIN" ]; then
  echo "❌ CF_TUNNEL_DOMAIN is not set in .env"
  echo "   Please add: CF_TUNNEL_DOMAIN=your.domain.com"
  exit 1
fi

echo "📋 Configuration (from .env):"
echo "   Tunnel Name: $TUNNEL_NAME"
echo "   Domain: $DOMAIN"
echo "   Local Port: $LOCAL_PORT_UI"
echo ""

# ==========================

echo "🔐 Step 1: Cloudflare login (browser will open if not already logged in)"
if [ ! -f "$CLOUDFLARED_DIR/cert.pem" ]; then
  cloudflared tunnel login
else
  echo "   ↳ Already logged in (cert.pem exists)"
fi

echo "🚇 Step 2: Creating tunnel: $TUNNEL_NAME"
# Check if tunnel already exists
if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
  echo "   ↳ Tunnel '$TUNNEL_NAME' already exists, skipping creation"
else
  cloudflared tunnel create "$TUNNEL_NAME"
fi

# Extract tunnel UUID
# Extract tunnel UUID
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')

if [ -z "$TUNNEL_ID" ]; then
  echo "❌ Failed to detect tunnel UUID"
  exit 1
fi

# Check for credentials file
CRED_FILE="$CLOUDFLARED_DIR/$TUNNEL_ID.json"
if [ ! -f "$CRED_FILE" ]; then
  echo "⚠️  Tunnel '$TUNNEL_NAME' exists ($TUNNEL_ID), but credentials file is missing at $CRED_FILE"
  echo "   ↳ Deleting stale tunnel..."
  cloudflared tunnel delete -f "$TUNNEL_ID" || true
  
  echo "   ↳ Recreating tunnel..."
  cloudflared tunnel create "$TUNNEL_NAME"
  
  # Re-fetch ID
  TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
  
  if [ -z "$TUNNEL_ID" ]; then
    echo "❌ Failed to detect new tunnel UUID after recreation"
    exit 1
  fi
fi

echo "🆔 Tunnel UUID: $TUNNEL_ID"

echo "🌐 Step 3: Creating DNS route for $DOMAIN"
cloudflared tunnel route dns "$TUNNEL_NAME" "$DOMAIN" || echo "   ↳ DNS route may already exist"

echo "📝 Step 4: Writing config.yml"
mkdir -p "$CLOUDFLARED_DIR"

cat > "$CONFIG_FILE" <<EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: $DOMAIN
    service: http://localhost:$LOCAL_PORT_UI
    originRequest:
      noTLSVerify: true

  - service: http_status:404
EOF

echo "✅ Config written to $CONFIG_FILE"

echo "⚙️ Step 5: Installing cloudflared as system service"
# Copy config to /etc/cloudflared for systemd service (sudo can't access ~/.cloudflared)
sudo mkdir -p /etc/cloudflared
sudo cp "$CONFIG_FILE" /etc/cloudflared/config.yml
sudo cp "$CLOUDFLARED_DIR/$TUNNEL_ID.json" /etc/cloudflared/
echo "   ↳ Copied credentials to /etc/cloudflared/"

sudo cloudflared service install || echo "   ↳ Service may already be installed"

echo "▶️ Step 6: Starting tunnel service"
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared

echo ""
echo "🎉 DONE!"
echo "👉 https://$DOMAIN → localhost:$LOCAL_PORT_UI (includes go2rtc via /api/go2rtc proxy)"
echo ""
echo "🔐 IMPORTANT - Set up Cloudflare Access:"
echo "   1. Go to: https://one.dash.cloudflare.com"
echo "   2. Access → Applications → Add an Application"
echo "   3. Type: Self-hosted"
echo "   4. Application domain: $DOMAIN"
echo "   5. Add authentication policy (email, Google, etc.)"
echo ""
echo "📡 Status commands:"
echo "   sudo systemctl status cloudflared"
echo "   journalctl -u cloudflared -f"

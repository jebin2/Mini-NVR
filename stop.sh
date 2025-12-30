#!/bin/bash
# ============================================
# Mini-NVR Stop Script
# Stops all Mini-NVR services
# ============================================

cd "$(dirname "${BASH_SOURCE[0]}")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
echo -e "${YELLOW}           Stopping Mini-NVR               ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════${NC}"
echo ""

# Stop Docker containers
echo -e "${YELLOW}📦 Stopping Docker containers...${NC}"
MINI_NVR_RUNNING=$(docker ps --filter "name=mini-nvr" --format "{{.Names}}" 2>/dev/null)
GO2RTC_RUNNING=$(docker ps --filter "name=go2rtc" --format "{{.Names}}" 2>/dev/null)

if [ -n "$MINI_NVR_RUNNING" ]; then
    docker stop mini-nvr >/dev/null 2>&1
    echo -e "  ${GREEN}✓${NC} Stopped mini-nvr"
else
    echo -e "  ${YELLOW}○${NC} mini-nvr was not running"
fi

if [ -n "$GO2RTC_RUNNING" ]; then
    docker stop go2rtc >/dev/null 2>&1
    echo -e "  ${GREEN}✓${NC} Stopped go2rtc"
else
    echo -e "  ${YELLOW}○${NC} go2rtc was not running"
fi
echo ""

# Stop YouTube Uploader Service
echo -e "${YELLOW}📤 Stopping YouTube Uploader...${NC}"
if systemctl is-active --quiet mini-nvr-uploader 2>/dev/null; then
    sudo systemctl stop mini-nvr-uploader
    echo -e "  ${GREEN}✓${NC} Stopped uploader (systemd)"
elif pgrep -f "youtube_uploader/main.py" > /dev/null 2>&1; then
    pkill -f "youtube_uploader/main.py"
    echo -e "  ${GREEN}✓${NC} Stopped uploader (manual)"
else
    echo -e "  ${YELLOW}○${NC} Uploader was not running"
fi
echo ""

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}           Mini-NVR Stopped                ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"

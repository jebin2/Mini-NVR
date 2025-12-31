#!/bin/bash
# Mini-NVR Status Check
# Shows status of all Mini-NVR services

cd "$(dirname "${BASH_SOURCE[0]}")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}          Mini-NVR Status Check            ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

# Docker containers
echo -e "${YELLOW}📦 Docker Containers:${NC}"
MINI_NVR_STATUS=$(docker ps --filter "name=mini-nvr" --format "{{.Names}}\t{{.Status}}" 2>/dev/null)
GO2RTC_STATUS=$(docker ps --filter "name=go2rtc" --format "{{.Names}}\t{{.Status}}" 2>/dev/null)

if [ -n "$MINI_NVR_STATUS" ] || [ -n "$GO2RTC_STATUS" ]; then
    echo -e "  NAME\t\tSTATUS"
    [ -n "$MINI_NVR_STATUS" ] && echo -e "  ${GREEN}✓${NC} $MINI_NVR_STATUS"
    [ -n "$GO2RTC_STATUS" ] && echo -e "  ${GREEN}✓${NC} $GO2RTC_STATUS"
else
    echo -e "  ${RED}✗ Not running${NC}"
fi
echo ""

# YouTube Uploader Status (now runs inside Docker)
echo -e "${YELLOW}📤 YouTube Uploader (Docker):${NC}"
if [ -n "$MINI_NVR_STATUS" ]; then
    # Check uploader status from Docker logs
    UPLOADER_STATUS=$(docker logs mini-nvr 2>&1 | grep -E "NVR Uploader.*Started|NVR Uploader.*Auth|NVR Uploader.*Stopped" | tail -1)
    if [ -n "$UPLOADER_STATUS" ]; then
        if echo "$UPLOADER_STATUS" | grep -q "Started"; then
            echo -e "  ${GREEN}✓ Running${NC}"
        elif echo "$UPLOADER_STATUS" | grep -q "Auth"; then
            echo -e "  ${YELLOW}⚠ Waiting for auth${NC}"
        else
            echo -e "  ${RED}✗ Stopped${NC}"
        fi
        echo "  $(echo "$UPLOADER_STATUS" | sed 's/^/  /')"
    else
        echo -e "  ${GREEN}✓ Running (in mini-nvr container)${NC}"
    fi
else
    echo -e "  ${RED}✗ Not running (mini-nvr container stopped)${NC}"
fi
echo ""

# Cloudflare Tunnel
echo -e "${YELLOW}🚇 Cloudflare Tunnel:${NC}"
if systemctl is-active --quiet cloudflared 2>/dev/null; then
    echo -e "  ${GREEN}✓ Running (systemd)${NC}"
    CF_TUNNEL_NAME=$(grep "tunnel:" ~/.cloudflared/config.yml 2>/dev/null | awk '{print $2}')
    [ -z "$CF_TUNNEL_NAME" ] && CF_TUNNEL_NAME=$(grep "tunnel:" /etc/cloudflared/config.yml 2>/dev/null | awk '{print $2}')
    
    if [ -n "$CF_TUNNEL_NAME" ]; then
        echo "  Tunnel ID: $CF_TUNNEL_NAME"
    fi
elif pgrep "cloudflared" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Running (process)${NC}"
else
    echo -e "  ${RED}✗ Not running${NC}"
fi
echo ""

# Recent logs
echo -e "${YELLOW}📜 Recent Uploader Logs:${NC}"
if [ -f "./logs/youtube_uploader.log" ]; then
    tail -5 ./logs/youtube_uploader.log 2>/dev/null | sed 's/^/  /'
elif [ -n "$MINI_NVR_STATUS" ]; then
    docker logs mini-nvr 2>&1 | grep "NVR Uploader" | tail -5 | sed 's/^/  /'
else
    echo "  No logs found"
fi
echo ""

# Auth logs
echo -e "${YELLOW}🔐 Recent Auth Logs:${NC}"
if [ -f "./logs/reauth.log" ]; then
    tail -3 ./logs/reauth.log 2>/dev/null | sed 's/^/  /'
else
    echo "  No auth logs"
fi
echo ""

# Disk usage
echo -e "${YELLOW}💾 Storage:${NC}"
if [ -d "./recordings" ]; then
    RECORDINGS_SIZE=$(du -sh ./recordings 2>/dev/null | cut -f1)
    RECORDINGS_COUNT=$(find ./recordings -name "*.mp4" 2>/dev/null | wc -l)
    echo "  Recordings: $RECORDINGS_SIZE ($RECORDINGS_COUNT files)"
fi
if [ -d "./logs" ]; then
    LOGS_SIZE=$(du -sh ./logs 2>/dev/null | cut -f1)
    echo "  Logs: $LOGS_SIZE"
fi
echo ""

echo -e "${BLUE}═══════════════════════════════════════════${NC}"


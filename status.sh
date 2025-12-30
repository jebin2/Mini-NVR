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
# Check for containers by name (works regardless of how they were started)
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

# YouTube Uploader Service
echo -e "${YELLOW}📤 YouTube Uploader Service:${NC}"
if systemctl is-active --quiet mini-nvr-uploader 2>/dev/null; then
    echo -e "  ${GREEN}✓ Running (systemd)${NC}"
    echo "  PID: $(pgrep -f 'youtube_uploader/main.py' 2>/dev/null || echo 'N/A')"
elif pgrep -f "youtube_uploader/main.py" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Running (manual)${NC}"
    echo "  PID: $(pgrep -f 'youtube_uploader/main.py')"
else
    echo -e "  ${RED}✗ Not running${NC}"
fi
echo ""

# Recent logs
echo -e "${YELLOW}📜 Recent Uploader Logs:${NC}"
if [ -f "./logs/youtube_uploader.log" ]; then
    tail -5 ./logs/youtube_uploader.log 2>/dev/null | sed 's/^/  /'
else
    echo "  No logs found"
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

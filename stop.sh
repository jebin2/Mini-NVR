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

# Stop and remove Docker containers (includes YouTube uploader)
# Using 'docker compose down' ensures containers are fully removed,
# which prevents volume mount caching issues when directories are deleted/recreated
echo -e "${YELLOW}📦 Stopping and removing Docker containers...${NC}"
docker compose down >/dev/null 2>&1

# Force-kill containers stuck due to hf-mount NFS mounts
for cid in $(docker ps -aq --filter "name=mini-nvr" 2>/dev/null); do
    # Try graceful remove first
    if ! docker rm -f "$cid" >/dev/null 2>&1; then
        echo -e "  ${YELLOW}⚠${NC} Container $cid stuck (NFS mount), force-killing..."
        # Kill container process at kernel level
        pid=$(docker inspect --format '{{.State.Pid}}' "$cid" 2>/dev/null)
        if [ -n "$pid" ] && [ "$pid" != "0" ]; then
            sudo kill -9 "$pid" 2>/dev/null || true
        fi
        # Lazy-unmount leftover NFS mounts inside container overlay
        for mnt in $(grep -s "recordings" /proc/mounts | grep overlay2 | awk '{print $2}'); do
            sudo umount -f -l "$mnt" 2>/dev/null || true
        done
        sleep 2
        docker rm -f "$cid" >/dev/null 2>&1 || true
    fi
done

echo -e "  ${GREEN}✓${NC} Stopped and removed all containers"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}           Mini-NVR Stopped                ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"



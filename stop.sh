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
echo -e "  ${GREEN}✓${NC} Stopped and removed all containers"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}           Mini-NVR Stopped                ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"



#!/bin/bash
# Wrapper to run reauth.py ensuring only one instance runs
# Runs on HOST

# Get the directory where this script is located (works from any cwd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAUTH_SCRIPT="$SCRIPT_DIR/reauth.py"

# Check if reauth.py is already running
if pgrep -f "python3.*reauth.py" > /dev/null; then
    echo "Reauth script is already running. Skipping."
    exit 0
fi

# Run reauth.py with absolute path
python3 "$REAUTH_SCRIPT"

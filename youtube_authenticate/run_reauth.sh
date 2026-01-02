#!/bin/bash
# Wrapper to run reauth.py ensuring only one instance runs
# Runs on HOST

# Check if reauth.py is already running
if pgrep -f "python3.*youtube_authenticate/reauth.py" > /dev/null; then
    echo "Reauth script is already running. Skipping."
    exit 0
fi

# Run reauth.py
python3 youtube_authenticate/reauth.py

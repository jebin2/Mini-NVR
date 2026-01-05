#!/bin/bash
# Wrapper to run reauth.py ensuring only one instance runs
# Runs on HOST

# Get the directory where this script is located (works from any cwd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
REAUTH_SCRIPT="$SCRIPT_DIR/reauth.py"

# Python with youtube_auto_pub installed (pyenv virtualenv named after project)
PYTHON="$HOME/.pyenv/versions/${PROJECT_NAME}_env/bin/python"

# Check if pyenv Python environment exists
if [ ! -f "$PYTHON" ]; then
    echo "[WARN] pyenv environment not found: $PYTHON"
    echo "[WARN] YouTube reauth requires pyenv setup. Skipping."
    exit 0
fi

# Check if reauth.py is already running
if pgrep -f "python.*reauth.py" > /dev/null; then
    echo "Reauth script is already running. Skipping."
    exit 0
fi

# Run reauth.py with the correct Python
"$PYTHON" "$REAUTH_SCRIPT"

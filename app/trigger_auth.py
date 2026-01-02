#!/usr/bin/env python3
"""
Trigger Auth via SSH
Running inside Docker. Connects to Host to run youtube_authenticate/run_reauth.sh
"""

import os
import sys
import subprocess
import logging

# Ensure app root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.config import settings

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='[TriggerAuth] %(message)s')
logger = logging.getLogger("trigger_auth")

def main():
    ssh_user = settings.ssh_host_user
    # PROJECT_DIR in Docker might not match Host, but we usually mount it same location or 
    # pass PROJECT_DIR env var to Docker. 
    # Use PROJECT_DIR env var if set, else default.
    project_dir = settings.project_dir
    
    if not project_dir:
        logger.error("PROJECT_DIR environment variable not set!")
        sys.exit(1)

    logger.info("🔐 Triggering SSH reauth on host...")
    logger.info(f"   User: {ssh_user}")
    logger.info(f"   Project: {project_dir}")

    # Command to run on host
    host_cmd = f"{project_dir}/youtube_authenticate/run_reauth.sh"

    cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10',
        f'{ssh_user}@host.docker.internal',
        host_cmd
    ]

    try:
        # Run SSH command
        # We wait for it to finish. run_reauth.sh handles singleton check.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout in case human is slow
        )

        if result.returncode == 0:
            logger.info("✓ SSH command executed successfully.")
            logger.info(f"  stdout: {result.stdout.strip()}")
            return 0
        else:
            logger.error(f"✗ SSH command failed (exit {result.returncode})")
            if result.stderr:
                logger.error(f"  stderr: {result.stderr.strip()}")
            return result.returncode

    except subprocess.TimeoutExpired:
        logger.error("✗ SSH command timed out (30 min)")
        return 1
    except Exception as e:
        logger.error(f"✗ Error executing SSH: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

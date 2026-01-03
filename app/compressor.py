#!/usr/bin/env python3
"""
Compressor Entry Point
Wraps app.services.compressor.BackgroundCompressor
"""

import os
import sys
import signal

# Get directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from core.config import settings
from core.logger import setup_logger
from services.compressor import BackgroundCompressor

log = setup_logger("compressor", "/logs/compressor.log")


def main():
    # Check if compressor should run
    if settings.inline_transcoding:
        print("[NVR Compressor] Inline transcoding enabled, compressor not needed")
        return
    
    if not settings.compressor_enabled:
        print("[NVR Compressor] Compressor disabled (COMPRESSOR_ENABLED != true)")
        return

    # Create service
    service = BackgroundCompressor(
        record_dir=settings.record_dir,
        video_codec=settings.video_codec,
        crf=int(settings.video_crf),
        preset=settings.video_preset
    )
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[NVR Compressor] Received signal {signum}, stopping...")
        service.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run (blocks until stopped)
    service.run()


if __name__ == "__main__":
    main()

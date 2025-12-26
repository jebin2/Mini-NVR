import logging
import sys
import os

def setup_logger(name, log_file=None):
    """
    Sets up a logger with the specified name and log file.
    If log_file is provided, logs will be written to that file as well.
    If log_file is None, it checks the LOG_FILE environment variable.
    If neither is provided, file logging is disabled (stdout only).
    """
    if log_file is None:
        log_file = os.getenv("LOG_FILE")

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = [] # Clear existing handlers

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console Handler (stdout)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        # Use append mode. The file clearing is handled at startup by the entrypoint.
        fh = logging.FileHandler(log_file, mode='a')
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

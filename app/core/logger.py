import logging
import sys
import os
from datetime import datetime

class Tee:
    """
    Redirect stdout/stderr to both terminal and log file.
    """
    def __init__(self, log_path, stream):
        self.log_path = log_path
        self.stream = stream
        self.log_file = open(log_path, 'a')
    
    def write(self, data):
        if data.strip():  # Only log non-empty lines
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Write to original stream
            self.stream.write(data)
            self.stream.flush()
            # Write to log file with timestamp (for lines that don't have one)
            for line in data.splitlines():
                if line.strip():
                    self.log_file.write(f"{timestamp} {line}\n")
            self.log_file.flush()
        else:
            self.stream.write(data)
            self.stream.flush()
    
    def flush(self):
        self.stream.flush()
        self.log_file.flush()
    
    def close(self):
        self.log_file.close()

def setup_stdout_capture(log_file):
    """
    Redirect sys.stdout and sys.stderr to a Tee instance for file capturing.
    """
    if not log_file:
        return
        
    # Ensure directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Redirect
    sys.stdout = Tee(log_file, sys.__stdout__)
    sys.stderr = Tee(log_file, sys.__stderr__)

def setup_logger(name, log_file=None):
    """
    Sets up a logger with the specified name and log file.
    If log_file is provided, logs will be written to that file as well.
    If log_file is None, it checks the LOG_FILE environment variable.
    If neither is provided, file logging is disabled (stdout only).
    """
    if log_file is None:
        # Import inside function to avoid circular import risks if config imports logger in future
        from core import config
        log_file = config.settings.log_file

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

FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app

# Copy application code
COPY app/ .

# Copy web UI
COPY web/ /app/web/

# Expose web port (default matches WEB_PORT in config)
EXPOSE 2126

# Start all services
CMD ["sh", "-c", "if [ -n \"$LOG_FILE\" ]; then rm -f \"$LOG_FILE\"; fi && python server.py & python recorder.py & python cleanup.py & wait"]

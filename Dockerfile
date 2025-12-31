FROM python:3.11-slim

# Install FFmpeg and SSH client (for Docker-to-host auth triggering)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git openssh-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install youtube_auto_pub for uploader
RUN pip install --no-cache-dir git+https://github.com/jebin2/youtube_auto_pub.git

WORKDIR /app

# Copy application code
COPY app/ .

# Copy web UI
COPY web/ /app/web/

# Copy youtube uploader
COPY youtube_uploader/ /app/youtube_uploader/

# Ensure Python output is not buffered (for real-time logs)
ENV PYTHONUNBUFFERED=1

# Expose web port (default matches WEB_PORT in config)
EXPOSE 2126

# Start all services including YouTube uploader
CMD ["sh", "-c", "if [ -n \"$LOG_FILE\" ]; then rm -f \"$LOG_FILE\"; fi && python server.py & python recorder.py & python cleanup.py & python youtube_uploader/main.py & wait"]

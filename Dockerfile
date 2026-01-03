FROM python:3.11-slim

# Install FFmpeg, SSH client, and Docker CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git openssh-client docker.io && \
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

# Ensure Python output is not buffered (for real-time logs)
ENV PYTHONUNBUFFERED=1

# Start all services including YouTube uploader
CMD ["./start_services.sh"]

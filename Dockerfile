FROM python:3.11-slim

# Install FFmpeg, SSH client, and Docker CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    openssh-client \
    docker.io \
    intel-media-va-driver \
    libva-drm2 \
    rsync \
    nfs-common \
    curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install hf-mount
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        HF_ARCH="x86_64-linux"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        HF_ARCH="aarch64-linux"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    curl -fsSL -O "https://github.com/huggingface/hf-mount/releases/latest/download/hf-mount-${HF_ARCH}" && \
    curl -fsSL -O "https://github.com/huggingface/hf-mount/releases/latest/download/hf-mount-nfs-${HF_ARCH}" && \
    chmod +x hf-mount-* && \
    mv hf-mount-${HF_ARCH} /usr/local/bin/hf-mount && \
    mv hf-mount-nfs-${HF_ARCH} /usr/local/bin/hf-mount-nfs

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

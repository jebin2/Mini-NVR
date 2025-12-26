# Mini-NVR

A lightweight, Docker-based Network Video Recorder for RTSP cameras.

## Features

- 📹 Multi-channel RTSP recording
- 📦 Configurable segment duration (MKV format)
- 🧹 Automatic cleanup when storage limit reached
- 🌐 Web-based recording viewer with controls
- 🎛️ Start/stop recording per channel or all
- 🗑️ Delete recordings from web UI

## Quick Start

### 1. Configure

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
nano .env
```

### 2. Run

**Development** (with live reload for web files):
```bash
docker compose up -d --build
```

**Production** (self-contained, no source files needed):
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 3. Access

Open `http://localhost:8080` (or your configured `WEB_PORT`)

## Deployment Options

| Mode | Command | Web files | Best for |
|------|---------|-----------|----------|
| **Development** | `docker compose up -d` | Volume-mounted (live reload) | Developing & customizing |
| **Production** | `docker compose -f docker-compose.prod.yml up -d` | Baked into image | Deploy without source code |

## Configuration

All configuration is done via `.env` file. **All variables are required.**

| Variable | Description |
|----------|-------------|
| `DVR_IP` | Camera/DVR IP address |
| `DVR_USER` | Username |
| `DVR_PASS` | Password |
| `DVR_PORT` | RTSP port (usually 554) |
| `RTSP_URL_TEMPLATE` | URL template (see below) |
| `NUM_CHANNELS` | Number of camera channels |
| `SEGMENT_DURATION` | Recording segment length in seconds |
| `RECORD_DIR` | Must be `/recordings` (container path) |
| `MAX_STORAGE_GB` | Max storage before auto-cleanup |
| `CLEANUP_INTERVAL` | Cleanup check interval in seconds |
| `WEB_PORT` | Web UI port |
| `API_PORT` | Internal API port (usually 8000) |

> **Note:** `RECORD_DIR` must remain `/recordings` as this is the path mounted inside the container.

### RTSP URL Templates

Use placeholders: `{user}`, `{pass}`, `{ip}`, `{port}`, `{channel}`

| Camera Type | Template |
|-------------|----------|
| Hikvision | `rtsp://{user}:{pass}@{ip}:{port}/Streaming/Channels/{channel}01` |
| Dahua | `rtsp://{user}:{pass}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0` |
| Generic | `rtsp://{user}:{pass}@{ip}:{port}/stream{channel}` |

## Development

### What needs rebuild?

| File | Rebuild? | Command |
|------|----------|---------|
| `app/*.py` | ✅ Yes | `docker compose build --no-cache && docker compose up -d` |
| `.env` | ❌ No | `docker compose restart` |
| `web/index.html` | ❌ No | Just refresh browser (dev mode only) |
| `web/nginx.conf` | ❌ No | `docker compose restart` (dev mode only) |

## Project Structure

```
├── .env                    # Configuration
├── .env.example            # Template
├── docker-compose.yml      # Development (with mounts)
├── docker-compose.prod.yml # Production (self-contained)
├── Dockerfile              # All-in-one image
├── app/
│   ├── api.py              # REST API
│   ├── recorder.py         # RTSP recording
│   └── cleanup.py          # Storage management
├── web/
│   ├── index.html          # Web UI
│   └── nginx.conf          # Nginx config
└── recordings/             # Video storage
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get configuration |
| GET | `/api/status` | Get recording status per channel |
| GET | `/api/storage` | Get storage usage |
| GET | `/api/files` | List recordings |
| POST | `/api/recording/start?channel=N` | Start recording (N or "all") |
| POST | `/api/recording/stop?channel=N` | Stop recording (N or "all") |
| DELETE | `/api/file?name=X` | Delete a recording |
| DELETE | `/api/files?channel=N` | Delete all channel N recordings |

## License

MIT

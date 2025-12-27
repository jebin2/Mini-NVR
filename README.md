# Mini-NVR

A lightweight, Docker-based Network Video Recorder for RTSP cameras with live streaming capabilities.

## Features

- 📹 **Multi-channel RTSP recording** with automatic MKV → MP4 conversion
- 🎥 **Live View** via WebRTC (low-latency, powered by go2rtc)
- 📺 **YouTube Live Streaming** with automatic 1-hour key rotation
- 🌐 **Web-based viewer** with timeline controls and playback
- 🔒 **Secure authentication** with rate limiting & CSRF protection
- 🧹 **Automatic cleanup** when storage limit reached
- � **Storage monitoring** dashboard

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              DVR                                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ RTSP (x1 per camera)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         go2rtc (Hub)                                │
│                    Single RTSP connection                           │
└───────┬─────────────────────┬─────────────────────┬─────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌──────────┐          ┌──────────┐
   │ WebRTC  │          │   RTSP   │          │   RTMP   │
   │  Live   │          │  Relay   │          │ YouTube  │
   │  View   │          │          │          │   Live   │
   └─────────┘          └────┬─────┘          └──────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   recorder.py   │
                    │  (MKV → MP4)    │
                    └─────────────────┘
```

**Benefits:**
- Single RTSP connection per camera (reduced CPU/bandwidth)
- go2rtc handles reconnection and buffering
- All consumers share one stream: live view, recording, YouTube

---

## Quick Start

### 1. Configure

```bash
cp .env.example .env
nano .env  # Edit DVR credentials and settings
```

**Required settings:**
```bash
DVR_IP=192.168.1.100
DVR_USER=admin
DVR_PASS=yourpassword
DVR_PORT=554
NUM_CHANNELS=8
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 2. Start

```bash
./scripts/start.sh -d
```

This will:
1. Generate `go2rtc.yaml` from your `.env`
2. Generate `web/js/config.js` with correct ports
3. Build and start Docker containers

### 3. Access

| Service | URL |
|---------|-----|
| **Web UI** | `http://localhost:2126` |
| **go2rtc Admin** | `http://localhost:2127` |

Default login: `admin` / `changeme` (configure in `.env`)

---

## Configuration

All configuration is done via `.env` file. Configs are auto-generated at startup.

### DVR Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DVR_IP` | Camera/DVR IP address | *required* |
| `DVR_USER` | Username | *required* |
| `DVR_PASS` | Password | *required* |
| `DVR_PORT` | RTSP port | `554` |
| `RTSP_URL_TEMPLATE` | URL template (see below) | Hikvision |
| `NUM_CHANNELS` | Number of camera channels | `8` |
| `SEGMENT_DURATION` | Recording segment (seconds) | `600` |
| `MAX_STORAGE_GB` | Max storage before cleanup | `500` |
| `WEB_PORT` | Web UI port | `2126` |

### go2rtc Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `GO2RTC_API_PORT` | go2rtc API/admin port | `2127` |
| `GO2RTC_WEBRTC_PORT` | WebRTC signaling port | `8555` |
| `GO2RTC_RTSP_PORT` | RTSP relay port | `8554` |

### YouTube Live Streaming

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_ENABLED` | Enable streaming | `false` |
| `YOUTUBE_STREAM_KEY_1` | First stream key | *required if enabled* |
| `YOUTUBE_STREAM_KEY_2` | Second key (rotation) | *required if enabled* |
| `YOUTUBE_CHANNEL` | Camera to stream | `1` |
| `YOUTUBE_ROTATION_MINUTES` | Rotation interval | `60` |

> **Setup:** Create 2 stream keys in [YouTube Studio](https://studio.youtube.com) → Create → Go Live → Stream.
> Keys rotate hourly to avoid YouTube's 12-hour session limit.

### Security Settings

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | **Required.** Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `user1`, `pass1` | Login credentials (add user2/pass2 for more) |

> **Production:** Use bcrypt-hashed passwords:
> ```bash
> python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
> ```

### RTSP URL Templates

Use placeholders: `{user}`, `{pass}`, `{ip}`, `{port}`, `{channel}`

| Camera | Template |
|--------|----------|
| Hikvision | `rtsp://{user}:{pass}@{ip}:{port}/Streaming/Channels/{channel}01` |
| Dahua | `rtsp://{user}:{pass}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0` |
| Generic | `rtsp://{user}:{pass}@{ip}:{port}/stream{channel}` |

---

## Project Structure

```
├── .env.example              # Configuration template
├── docker-compose.yml        # Container orchestration
├── Dockerfile                # NVR container image
├── scripts/
│   ├── start.sh              # Main startup script
│   ├── generate-go2rtc-config.sh
│   └── generate-web-config.sh
├── app/
│   ├── server.py             # FastAPI web server
│   ├── recorder.py           # RTSP recording (via go2rtc)
│   ├── cleanup.py            # Storage management
│   ├── api/                  # REST endpoints
│   ├── core/                 # Config, logging, security
│   └── services/
│       ├── converter.py      # MKV → MP4 converter
│       ├── youtube_rotator.py # YouTube stream rotation
│       └── ...
├── web/                      # Frontend (HTML/CSS/JS)
├── recordings/               # Video storage (volume)
└── go2rtc.yaml               # Auto-generated
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/login` | Login (rate limited: 5/min) |
| POST | `/api/logout` | Logout |
| GET | `/api/me` | Get current user |

### Protected Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | System configuration |
| GET | `/api/storage` | Storage usage |
| GET | `/api/live` | Live channel status |
| GET | `/api/dates` | Available recording dates |
| GET | `/api/channel/{ch}/recordings` | Recordings for channel/date |
| DELETE | `/api/recording?path=...` | Delete a recording |

---

## Development

### Common Commands

```bash
# Start (foreground, see logs)
./scripts/start.sh

# Start (background)
./scripts/start.sh -d

# View logs
docker compose logs -f

# Restart after .env change
docker compose restart

# Rebuild after code change
docker compose down && docker compose up -d --build
```

### What Needs Rebuild?

| Change | Rebuild? | Command |
|--------|----------|---------|
| `app/*.py` | ✅ Yes | `docker compose up -d --build` |
| `.env` | ❌ No | `docker compose restart` |
| `web/**` | ❌ No | Refresh browser |
| go2rtc ports | ⚠️ Regenerate | `./scripts/start.sh -d` |

---

## Security Features

- **Password Hashing**: bcrypt support for production
- **Session Management**: Server-side validation, max 5 sessions/user
- **Rate Limiting**: Login limited to 5 attempts/minute
- **CSRF Protection**: Double Submit Cookie pattern
- **Input Validation**: All parameters validated

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Live view not connecting | Check `GO2RTC_API_PORT` matches in browser console |
| Recording not starting | Verify go2rtc is running: `docker logs go2rtc` |
| YouTube not streaming | Ensure `YOUTUBE_ENABLED=true` and keys configured |
| Port conflicts | Change ports in `.env`, run `./scripts/start.sh -d` |

---

## License

MIT

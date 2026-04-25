# Mini-NVR

A lightweight, Docker-based Network Video Recorder for RTSP cameras with live streaming capabilities.

## Features

- 📹 **Multi-channel RTSP recording** with automatic MKV → MP4 conversion
- 🎥 **Live View** via WebRTC (low-latency, powered by go2rtc)
- 📺 **YouTube Live Streaming** with hourly video segmentation (per channel)
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

### Playback Architecture

Mini-NVR offloads recorded video playback directly to Hugging Face (HF) CDN to save server bandwidth. 

- **Live View (Grid):** Streams in real-time via WebRTC (powered by go2rtc).
- **Recorded Playback:** The UI constructs direct Hugging Face CDN URLs (`master.m3u8`). The video flows directly from HF to the client browser, completely bypassing the NVR server.
- **Playlist Regeneration:** The VOD playlist (`playlist.m3u8`) is regenerated and synced to Hugging Face every **5 minutes**. As a result, "Go to Live" in the expanded player (which uses the VOD playlist) may be up to 5-6 minutes behind real-time.

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
./start.sh -d
```

This will:
1. Generate `go2rtc.yaml` from your `.env`
2. Generate `web/js/config.js` with correct ports
3. Build and start Docker containers

### 3. Access

| Service | URL |
|---------|-----|
| **Web UI** | `http://localhost:web_port` |
| **go2rtc Admin** | `http://localhost:go2rtc_api_port` |

Default login: `admin` / `changeme` (configure in `.env`)

### 4. Remote Access (Optional)

Securely access your NVR from anywhere using Cloudflare Tunnel (no port forwarding required).

```bash
./scripts/setup_cloudflare_tunnel.sh
```

- **URL:** `https://cctv.yourdomain.com`
- **Security:** Protected by Cloudflare Access (requires setup) + NVR Login

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
| `SEGMENT_DURATION` | Recording segment (seconds) | `10` |
| `MAX_STORAGE_GB` | Max storage before cleanup | `500` |
| `WEB_PORT` | Web UI port | `web_port` |

### go2rtc Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `GO2RTC_API_PORT` | go2rtc API/admin port | `go2rtc_api_port` |
| `GO2RTC_WEBRTC_PORT` | WebRTC signaling port | `go2rtc_webrtc_port` |
| `GO2RTC_RTSP_PORT` | RTSP relay port | `go2rtc_rtsp_port` |

### YouTube Live Streaming

Stream cameras to YouTube Live with automatic hourly segmentation.

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_LIVE_ENABLED` | Enable streaming | `false` |
| `YOUTUBE_STREAM_KEY_1` | Stream key for cam1 | - |
| `YOUTUBE_STREAM_KEY_2` | Stream key for cam2 | - |
| ... | ... | ... |
| `YOUTUBE_STREAM_KEY_8` | Stream key for cam8 | - |
| `YOUTUBE_ROTATION_HOURS` | Segment duration | `11` |
| `YOUTUBE_RTMP_URL` | RTMP ingest URL | `rtmp://a.rtmp.youtube.com/live2` |

**How it works:**
- Each channel gets its own stream key (1:1 mapping)
- Streams restart every hour (configurable) creating separate YouTube videos
- Great for archiving: each hour becomes a separate video on YouTube

> **Setup:** Create stream keys in [YouTube Studio](https://studio.youtube.com) → Create → Go Live → Stream.
> You only need to configure stream keys for the channels you want to stream.

### YouTube Video Upload (Recorded Videos)

Automatically upload converted MP4 recordings to YouTube.

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_UPLOAD_ENABLED` | Enable video uploading | `false` |
| `YOUTUBE_CLIENT_SECRET_PATH` | Path to client_secret.json | `./client_secret.json` |
| `YOUTUBE_TOKEN_PATH` | OAuth token storage | `./yttoken.json` |
| `YOUTUBE_VIDEO_PRIVACY` | Video privacy status | `unlisted` |
| `YOUTUBE_DELETE_AFTER_UPLOAD` | Delete local file after upload | `false` |
| `YOUTUBE_UPLOAD_INTERVAL` | Seconds between upload scans | `60` |
| `GOOGLE_EMAIL` | Google account email for OAuth | - |
| `GOOGLE_PASSWORD` | Google account password/app password | - |

**Setup:**

1. **Create Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the YouTube Data API v3

2. **Create OAuth Credentials:**
   - Go to APIs & Services → Credentials
   - Create OAuth 2.0 Client ID (Desktop application)
   - Download `client_secret.json` to project root

3. **Configure:**
   ```bash
   YOUTUBE_UPLOAD_ENABLED=true
   YOUTUBE_CLIENT_SECRET_PATH=./client_secret.json
   YOUTUBE_VIDEO_PRIVACY=unlisted  # or private/public
   ```

4. **First Run:**
   - On first start, you'll need to complete OAuth in the browser
   - Token will be saved for future use

> **Video Metadata:** Videos are automatically titled with channel, date, and time.
> Example: "NVR Channel 1 - 2025-12-28 23:31:27"

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
├── app/
│   ├── server.py             # FastAPI web server
│   ├── recorder.py           # RTSP recording (via go2rtc)
│   ├── cleanup.py            # Storage management
│   ├── api/                  # REST endpoints
│   ├── core/                 # Config, logging, security
│   └── services/
│       ├── converter.py      # MKV → MP4 converter
│       ├── youtube_rotator.py # YouTube live stream rotation
│       ├── youtube_uploader.py # Upload recordings to YouTube
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
./start.sh

# Start (background)
./start.sh -d

# Start with clean logs/recordings
./start.sh -cd

# Stop all services
./stop.sh

# Check status
./status.sh

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
| go2rtc ports | ⚠️ Regenerate | `./start.sh -d` |

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
| YouTube not streaming | Ensure `YOUTUBE_LIVE_ENABLED=true` and keys configured |
| Port conflicts | Change ports in `.env`, run `./start.sh -d` |

---

## License

MIT

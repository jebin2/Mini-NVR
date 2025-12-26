# Mini-NVR

A lightweight, Docker-based Network Video Recorder for RTSP cameras.

## Features

- 📹 Multi-channel RTSP recording
- 📦 Configurable segment duration (MKV → MP4 auto-conversion)
- 🧹 Automatic cleanup when storage limit reached
- 🌐 Web-based recording viewer with timeline controls
- 🔒 Session-based authentication with rate limiting & CSRF protection
- � Storage usage monitoring

## Quick Start

### 1. Configure

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
nano .env
```

### 2. Run

```bash
docker compose up -d --build
```

### 3. Access

Open `http://localhost:2126` (or your configured `WEB_PORT`)

## Configuration

All configuration is done via `.env` file.

### DVR Settings

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
| `WEB_PORT` | Web UI port (default: 2126) |

### Security Settings

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | **Required** for session security. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `user1`, `pass1` | First user credentials (add user2/pass2 for more users) |

> **Note:** For production, use bcrypt-hashed passwords. Generate with:
> ```bash
> python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
> ```

### RTSP URL Templates

Use placeholders: `{user}`, `{pass}`, `{ip}`, `{port}`, `{channel}`

| Camera Type | Template |
|-------------|----------|
| Hikvision | `rtsp://{user}:{pass}@{ip}:{port}/Streaming/Channels/{channel}01` |
| Dahua | `rtsp://{user}:{pass}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0` |
| Generic | `rtsp://{user}:{pass}@{ip}:{port}/stream{channel}` |

## Project Structure

```
├── .env                    # Configuration
├── .env.example            # Template
├── docker-compose.yml      # Docker compose config
├── Dockerfile              # Container image definition
├── requirements.txt        # Python dependencies
├── app/
│   ├── server.py           # FastAPI web server
│   ├── recorder.py         # RTSP recording service
│   ├── cleanup.py          # Storage management service
│   ├── api/
│   │   ├── auth.py         # Authentication endpoints
│   │   ├── routes.py       # API routes
│   │   └── deps.py         # Request dependencies (auth, CSRF)
│   ├── core/
│   │   ├── config.py       # Configuration loader
│   │   ├── logger.py       # Logging setup
│   │   └── security.py     # Session & password management
│   ├── services/
│   │   ├── store.py        # Recording storage queries
│   │   ├── converter.py    # MKV → MP4 background converter
│   │   ├── metadata.py     # Duration cache
│   │   └── media.py        # FFprobe utilities
│   └── utils/
│       └── helpers.py      # Utility functions
├── web/
│   ├── index.html          # Main UI
│   ├── login.html          # Login page
│   ├── css/styles.css      # Styles
│   └── js/                 # JavaScript modules
└── recordings/             # Video storage (mounted volume)
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/login` | Login (rate limited: 5/min) |
| POST | `/api/logout` | Logout |
| GET | `/api/me` | Get current user |

### Protected Routes (require authentication)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get system configuration |
| GET | `/api/storage` | Get storage usage |
| GET | `/api/live` | Get live channel status |
| GET | `/api/dates` | Get available recording dates |
| GET | `/api/channel/{ch}/recordings` | Get recordings for a channel/date |
| DELETE | `/api/recording?path=...` | Delete a non-live recording |

## Development

### What needs rebuild?

| File | Rebuild? | Command |
|------|----------|---------|
| `app/*.py` | ✅ Yes | `docker compose build --no-cache && docker compose up -d` |
| `.env` | ❌ No | `docker compose restart` |
| `web/**` | ❌ No | Just refresh browser |

## Security Features

- **Password Hashing**: Supports bcrypt-hashed passwords
- **Session Management**: Server-side session validation with max 5 sessions per user
- **Rate Limiting**: Login endpoint limited to 5 attempts per minute
- **CSRF Protection**: Double Submit Cookie pattern
- **Input Validation**: Channel and date parameters validated

## License

MIT


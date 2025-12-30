# Mini-NVR Design & Architecture

## System Overview

Mini-NVR is a lightweight, Docker-based Network Video Recorder designed for efficiency and modern integration. It leverages **go2rtc** as a central media hub to minimize connections to camera hardware while offering low-latency WebRTC live viewing, continuous recording, and cloud integration (YouTube Live & Upload).

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "📹 Camera Layer"
        DVR["DVR/IP Cameras<br/>(RTSP Source)"]
    end

    subgraph "🔄 Media Hub (Docker Host Network)"
        Go2RTC["**go2rtc**<br/>Single RTSP Connection<br/>Multi-Consumer Distribution"]
    end

    subgraph "🐳 Mini-NVR Container"
        Server["FastAPI Server<br/>(Auth, API, UI)"]
        Recorder["Recorder Service<br/>(FFmpeg → MKV)"]
        Converter["Converter Service<br/>(MKV → MP4)"]
        YTRotator["YouTube Rotator<br/>(Live Streaming)"]
        Cleanup["Cleanup Service<br/>(Storage Mgmt)"]
    end

    subgraph "💾 Storage"
        Disk[("recordings/<br/>ch{X}/{DATE}/*.mp4")]
    end

    subgraph "☁️ Cloud Services"
        YTLive["YouTube Live<br/>(RTMP)"]
        YTUpload["YouTube Videos<br/>(API Upload)"]
    end

    subgraph "🖥️ Host Services"
        Uploader["YouTube Uploader<br/>(Standalone Python)"]
        Neko["Neko Browser<br/>(OAuth Automation)"]
    end

    DVR -->|RTSP x1| Go2RTC
    Go2RTC -->|WebRTC| Server
    Go2RTC -->|RTSP Relay| Recorder
    Go2RTC -->|RTMP| YTRotator

    Recorder -->|Write .mkv| Disk
    Converter -->|Convert| Disk
    Cleanup -->|Delete Old| Disk

    YTRotator -->|Stream| YTLive
    Disk -->|Read .mp4| Uploader
    Uploader -->|Upload API| YTUpload
    Neko -.-|OAuth| Uploader

    style Go2RTC fill:#f9f,stroke:#333,stroke-width:2px
    style Uploader fill:#bfb,stroke:#333,stroke-width:2px
    style Server fill:#bbf,stroke:#333,stroke-width:2px
```

---

## Core Components

### 1. go2rtc (Media Hub)
| Aspect | Description |
|--------|-------------|
| **Role** | Central hub for all video streams |
| **Function** | RTSP connection pooling, WebRTC transcoding, RTSP relay |
| **Key Benefit** | Single connection per camera → serves multiple consumers |

### 2. Mini-NVR Container
| Service | Description |
|---------|-------------|
| **FastAPI Server** | Web UI, REST API, authentication, session management |
| **Recorder** | Captures RTSP from go2rtc, writes segmented MKV files |
| **Converter** | Background thread: MKV → MP4 using FFmpeg |
| **YouTube Rotator** | Manages live streams with hourly rotation |
| **Cleanup** | Two-stage storage management (upload-aware) |

### 3. YouTube Uploader (Host)
| Aspect | Description |
|--------|-------------|
| **Location** | Runs on host (not Docker) for browser automation |
| **Function** | Batch, merge, and upload MP4s to YouTube |
| **OAuth** | Uses Neko browser for token refresh automation |

---

## Detailed Workflows

### 1. 📹 Recording Pipeline

```mermaid
sequenceDiagram
    participant DVR as DVR/Camera
    participant Go2RTC as go2rtc
    participant Recorder as recorder.py
    participant Disk as Storage
    participant Converter as converter.py

    Note over DVR,Go2RTC: Single RTSP connection
    DVR->>Go2RTC: RTSP Stream (continuous)
    
    loop Every SEGMENT_DURATION (10 min)
        Go2RTC->>Recorder: RTSP relay (localhost:8554)
        Recorder->>Disk: Write ch{X}/{DATE}/{TIME}.mkv
        Note over Recorder,Disk: FFmpeg: -c copy -f matroska
    end

    loop File Watcher
        Converter->>Disk: Detect completed .mkv
        Converter->>Disk: Convert to .mp4
        Converter->>Disk: Delete original .mkv
    end
```

**Step-by-Step:**
1. **DVR → go2rtc**: Single RTSP connection established per camera
2. **go2rtc → Recorder**: Local RTSP relay on `localhost:8554`
3. **Recorder**: FFmpeg captures stream in 10-minute segments (MKV)
4. **Converter**: Watches for completed MKV files, converts to MP4
5. **File Organization**: `recordings/ch{X}/{YYYY-MM-DD}/{HH-MM-SS}.mp4`

---

### 2. 🧹 Storage Cleanup Pipeline

```mermaid
flowchart TD
    Start([Every 60s]) --> CheckSize[Calculate Storage Usage]
    CheckSize --> Compare1{Size > MAX_GB?}
    
    Compare1 -->|No| Sleep([Sleep 60s])
    Compare1 -->|Yes| Stage1[Stage 1: Safe Cleanup]
    
    Stage1 --> YTEnabled{YouTube Upload Enabled?}
    
    YTEnabled -->|Yes| FindUploaded[Find *_uploaded.mp4 files]
    YTEnabled -->|No| DeleteOldest50[Delete 50% oldest files]
    
    FindUploaded --> HasUploaded{Found uploaded files?}
    HasUploaded -->|Yes| DeleteUploaded[Delete up to 10 uploaded files]
    HasUploaded -->|No| Warning[⚠️ Log: Waiting for uploader...]
    
    DeleteUploaded --> ReCheck[Re-calculate Storage]
    DeleteOldest50 --> Sleep
    Warning --> Stage2Check
    
    ReCheck --> Stage2Check{Size > MAX + BUFFER?}
    Stage2Check -->|No| Sleep
    Stage2Check -->|Yes| Critical[🚨 CRITICAL: Delete 5 oldest files]
    Critical --> Sleep

    style Critical fill:#f99,stroke:#f00,stroke-width:2px
    style Stage1 fill:#ff9,stroke:#990,stroke-width:2px
```

**Step-by-Step:**
1. **Check**: Calculate total storage usage every 60 seconds
2. **Stage 1 (Soft Limit)**: If over `MAX_STORAGE_GB`:
   - YouTube mode: Delete only `*_uploaded.mp4` files (safe to remove)
   - Standard mode: Delete 50% of oldest files
3. **Stage 2 (Critical)**: If over `MAX_STORAGE_GB + MAX_STORAGE_EXCEED_ALLOWED_GB`:
   - Force delete oldest 5 files regardless of upload status
   - Logs critical warning to prevent system failure

---

### 3. 📤 YouTube Upload Pipeline

```mermaid
sequenceDiagram
    participant Disk as Storage
    participant Scanner as File Scanner
    participant Batcher as Batch Logic
    participant Merger as FFmpeg Merge
    participant API as YouTube API
    participant Neko as Neko Browser

    loop Every UPLOAD_INTERVAL (60s)
        Scanner->>Disk: Find stable .mp4 files
        Note over Scanner: Exclude *_uploaded.mp4
        
        Scanner->>Batcher: Group by channel + date
        
        alt Duration > 11.5 hours
            Batcher->>Batcher: Split into Part 1, Part 2...
        end
        
        loop Each Batch
            Batcher->>Merger: Create merge list
            Merger->>Disk: Write merged_{ID}.mp4
            
            Merger->>API: Upload video
            Note over API: Title: "NVR Channel X - YYYY-MM-DD"<br/>Description: Timestamps for each clip
            
            alt OAuth Token Expired
                API->>Neko: Trigger browser automation
                Neko->>API: New access token
            end
            
            API->>Disk: Rename originals to *_uploaded.mp4
            Merger->>Disk: Delete merged temp file
        end
    end
```

**Step-by-Step:**
1. **Scan**: Find all stable MP4 files (not being written)
2. **Filter**: Exclude already-uploaded files (`*_uploaded.mp4`)
3. **Group**: Batch files by Channel + Date
4. **Duration Check**: 
   - If total duration < 11.5 hours → single upload
   - If > 11.5 hours → split into multiple parts
5. **Merge**: FFmpeg concat files into single video
6. **Upload**: Push to YouTube with auto-generated title + timestamps
7. **Finalize**: Rename source files to `*_uploaded.mp4`

---

### 4. 📺 YouTube Live Streaming

```mermaid
sequenceDiagram
    participant Go2RTC as go2rtc
    participant Rotator as youtube_rotator.py
    participant FFmpeg as FFmpeg Process
    participant YT as YouTube RTMP

    Rotator->>Go2RTC: Request RTSP stream
    Rotator->>FFmpeg: Start RTMP push
    FFmpeg->>YT: Stream to rtmp://a.rtmp.youtube.com/live2/{KEY}

    Note over Rotator: Timer: ROTATION_MINUTES (60 min)
    
    loop Hourly Rotation
        Rotator->>FFmpeg: Stop process (graceful)
        Note over YT: Stream ends → Auto-save as VOD
        Rotator->>FFmpeg: Start new process
        FFmpeg->>YT: New stream session
    end
```

**Step-by-Step:**
1. **Configure**: Set stream keys in `.env` (one per channel)
2. **Start**: FFmpeg pushes RTSP → RTMP to YouTube
3. **Rotation**: Every 60 minutes (configurable):
   - Stop current stream (YouTube saves as VOD)
   - Start new stream session
4. **Result**: Each hour becomes a separate archived video on YouTube

---

### 5. 🔐 Authentication Flow

```mermaid
sequenceDiagram
    participant User as Browser
    participant UI as Web UI
    participant API as FastAPI
    participant Session as Session Store

    User->>UI: Navigate to /
    UI->>API: GET /api/me
    API-->>UI: 401 Unauthorized
    UI->>User: Redirect to /login.html

    User->>API: POST /api/login {user, pass, csrf}
    Note over API: Rate limit: 5/min
    
    alt Valid Credentials
        API->>Session: Create session
        API-->>User: Set-Cookie: session_id
        User->>UI: Redirect to /
    else Invalid
        API-->>User: 401 + remaining attempts
    end

    User->>API: GET /api/recordings
    API->>Session: Validate session_id
    Session-->>API: User info
    API-->>User: 200 + data
```

---

## Directory Structure

```
Mini-NVR/
├── 📄 .env                      # Configuration (secrets, settings)
├── 📄 .env.example              # Template configuration
├── 📄 docker-compose.yml        # Container orchestration
├── 📄 Dockerfile                # NVR container build
├── 📄 go2rtc.yaml               # Auto-generated from .env
│
├── 📁 app/                      # Main application
│   ├── server.py                # FastAPI entry point
│   ├── recorder.py              # RTSP recording service
│   ├── cleanup.py               # Storage management
│   ├── 📁 api/
│   │   ├── auth.py              # Login/logout endpoints
│   │   ├── routes.py            # API routes
│   │   └── deps.py              # Dependencies/middleware
│   ├── 📁 core/
│   │   ├── config.py            # Environment config loader
│   │   ├── logger.py            # Logging setup
│   │   └── security.py          # Auth, CSRF, rate limiting
│   └── 📁 services/
│       ├── converter.py         # MKV → MP4 conversion
│       ├── youtube_rotator.py   # Live stream rotation
│       └── store.py             # Recording metadata
│
├── 📁 web/                      # Frontend
│   ├── index.html               # Main viewer page
│   ├── login.html               # Login page
│   ├── 📁 css/                  # Stylesheets
│   └── 📁 js/                   # JavaScript modules
│
├── 📁 youtube_uploader/         # Standalone uploader (host)
│   └── main.py                  # NVRUploaderService class
│
├── 📁 scripts/                  # Setup & control
│   ├── start.sh                 # Main startup script
│   ├── generate-go2rtc-config.sh
│   └── generate-web-config.sh
│
└── 📁 recordings/               # Video storage (Docker volume)
    └── ch{X}/
        └── {YYYY-MM-DD}/
            └── {HH-MM-SS}.mp4
```

---

## Data Flow Summary

| Source | Protocol | Destination | Purpose |
|--------|----------|-------------|---------|
| DVR | RTSP | go2rtc | Stream ingestion |
| go2rtc | WebRTC | Browser | Live view |
| go2rtc | RTSP | recorder.py | Recording |
| go2rtc | RTMP | YouTube | Live streaming |
| Disk | File | converter.py | MKV → MP4 |
| Disk | File | uploader | YouTube upload |

---

## Security Architecture

```mermaid
flowchart LR
    subgraph "Client"
        Browser[Browser]
    end

    subgraph "Server"
        CSRF[CSRF Token<br/>Double Submit]
        Rate[Rate Limiter<br/>5 req/min login]
        Session[Session Store<br/>Max 5/user]
        Auth[Auth Middleware]
    end

    Browser -->|1. GET /login| CSRF
    CSRF -->|2. Set csrf_token cookie| Browser
    Browser -->|3. POST /api/login + csrf| Rate
    Rate --> Auth
    Auth -->|4. Validate| Session
    Session -->|5. Set session_id| Browser
```

**Features:**
- ✅ Bcrypt password hashing
- ✅ Session-based authentication (max 5 per user)
- ✅ CSRF protection (Double Submit Cookie)
- ✅ Rate limiting (login: 5 attempts/minute)
- ✅ Input validation on all parameters

---

## Configuration Reference

See [README.md](./README.md#configuration) for complete environment variable reference.

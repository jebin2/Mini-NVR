# Mini-NVR Design & Architecture

## System Overview

Mini-NVR is a lightweight, Docker-based Network Video Recorder designed for efficiency and modern integration. It leverages **go2rtc** as a central media hub to minimize connections to camera hardware while offering low-latency WebRTC live viewing, continuous recording, and cloud integration (YouTube Live & Upload).

## Architecture Diagram

```mermaid
graph TD
    subgraph "Camera Layer"
        Cam1[Camera 1] -->|RTSP| Go2RTC
        Cam2[Camera 2] -->|RTSP| Go2RTC
        CamN[Camera N] -->|RTSP| Go2RTC
    end

    subgraph "Core Service (Docker Host Network)"
        Go2RTC[**go2rtc**<br/>(Media Hub)]
        
        Go2RTC -->|WebRTC| LiveView[Live UI]
        Go2RTC -->|RTMP| YTLive[YouTube Live]
        Go2RTC -->|RTSP| Recorder[**Recorder Service**<br/>(FFmpeg)]
    end

    subgraph "Storage & Processing"
        Recorder -->|Writes .mkv| Disk[(Recordings Dir)]
        
        Converter[**Converter Service**]
        Disk -->|Watch .mkv| Converter
        Converter -->|Convert to .mp4| Disk
        
        Cleanup[**Cleanup Service**]
        Disk -->|Monitor Usage| Cleanup
        Cleanup -->|Delete Old| Disk
    end

    subgraph "Cloud Integration (Host Side)"
        Uploader[**YouTube Uploader**<br/>(Standalone Python)]
        Disk -->|Read .mp4| Uploader
        Uploader -->|Upload| YTData[YouTube Channel]
        
        Neko[Neko Browser] -.->|OAuth| Uploader
    end

    style Go2RTC fill:#f9f,stroke:#333
    style Recorder fill:#bbf,stroke:#333
    style Uploader fill:#bfb,stroke:#333
```

## Core Components

### 1. go2rtc (Media Server)
- **Role**: Central hub for all video streams.
- **Function**: Connection multiplexing, WebRTC low-latency streaming, RTSP relay.
- **Benefit**: Connects to each camera ONCE, serves multiple consumers (Live View, Recorder, YouTube Live) without overloading the camera.

### 2. Mini-NVR Container
Runs the main application logic:
- **Server**: FastAPI backend for UI, authentication, and API.
- **Recorder**: Connects to local go2rtc streams and saves raw footage (MKV) to disk.
- **Converter**: Background thread that detects completed MKV segments and converts them to standard MP4.
- **YouTube Rotator**: Manages YouTube Live streams, restarting them hourly to create archive segments.
- **Cleanup**: Monitors disk usage and deletes old footage based on configured rules.

### 3. YouTube Uploader (Host Service)
- **Role**: Uploads recorded MP4s to YouTube.
- **Why Host?**: Runs outside Docker to support browser automation (Neko) for Google OAuth re-authentication if tokens expire.
- **Logic**: 
    - Batches clips by Channel & Date.
    - Merges clips if total duration < 12 hours.
    - Splits into "Part X" if > 11.5 hours.
    - Uploads with detailed timestamps.

## Workflows

### 1. Recording Pipeline
1. **Source**: `recorder.py` pulls RTSP stream from `localhost:8554` (go2rtc).
2. **Capture**: Saves chunks of video (default 10 mins) as `.mkv`.
3. **Conversion**: `converter.py` watches for closed `.mkv` files -> `ffmpeg` -> `.mp4`.
4. **Storage**: Files organized in `recordings/ch{X}/{DATE}/{TIME}.mp4`.

### 2. Storage Management (Cleanup)
The `cleanup.py` service runs the following logic every 60s:

```mermaid
graph TD
    Start[Check Storage Usage] -->|Size > MAX_GB?| Check1
    Check1{Yes} -->|Stage 1| SafeDelete
    Check1{No} --> Sleep
    
    SafeDelete[Find Uploaded Files<br/>(_uploaded.mp4)] -->|Found?| DeleteUploaded[Delete Uploaded Files]
    DeleteUploaded --> Sleep
    
    SafeDelete -->|None Found?| CheckCrit
    CheckCrit{Size > MAX + BUFFER?} -->|Yes| CriticalDelete[**CRITICAL DELETE**<br/>Delete OLDEST files indiscriminately]
    CheckCrit{No} --> Wait[Wait for Uploader] --> Sleep
```

### 3. YouTube Upload Pipeline
1. **Watch**: Service scans `recordings/` for stable MP4 files.
2. **Batch**: Groups files by `Channel` and `Date`.
3. **Check**: 
   - If total duration > 11.5h -> Split into [Batch 1, Batch 2...].
4. **Merge**: `ffmpeg concat` files into a single temporary MP4.
5. **Upload**: Uploads to YouTube via API.
6. **Finalize**: 
   - Rename source files to `*_uploaded.mp4`.
   - `cleanup.py` is now allowed to delete them.

### 4. YouTube Live Streaming
1. **Config**: User provides Stream Keys in `.env`.
2. **Rotation**: `youtube_rotator.py` starts an FFmpeg process pushing stream to `rtmp://a.rtmp.youtube.com/live2`.
3. **Archiving**: Every 60 mins (configurable), the stream is stopped and restarted.
4. **Result**: YouTube automatically saves the session as a VOD (Video on Demand) in your channel history.

## Directory Structure

```
/home/jebin/git/Mini-NVR/
├── .env                    # Secrets & Config
├── recording/              # Video Storage Volume
├── app/                    # Application Source
├── youtube_uploader/       # Uploader Source
└── scripts/                # Control Scripts
```

import subprocess
import time
import os
import re
import json
import threading
import glob
from datetime import datetime
from core import config
from core.logger import setup_logger

logger = setup_logger("recorder", "/logs/recorder.log")

def is_stopped(channel):
    """Check if channel recording is stopped."""
    return os.path.exists(os.path.join(config.settings.control_dir, f"stop_ch{channel}"))


def build_rtsp_url(template, user, password, ip, port, channel):
    """Build RTSP URL from template (for direct DVR connection)."""
    return template.format(
        user=user,
        **{"pass": password},
        ip=ip,
        port=port,
        channel=channel
    )


def build_go2rtc_url(channel):
    """Build RTSP URL from go2rtc relay (unified hub architecture)."""
    return f"rtsp://localhost:{config.settings.go2rtc_rtsp_port}/cam{channel}"


def ensure_dir(path):
    """Ensure directory exists, create if deleted."""
    if not os.path.exists(path):
        # Only print if we are actually creating it (reduces log spam)
        try:
            os.makedirs(path, exist_ok=True)

            logger.info(f"[📁] Created directory: {path}")
        except OSError:
            pass


def get_output_dir(base_dir, channel):
    """Get channel/date organized output directory."""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base_dir, f"ch{channel}", today)


def get_latest_file(out_dir, channel):
    """Get the latest recording file (TS segment or legacy MP4) for a channel."""
    # Check for HLS segments (.ts) or legacy MP4 files
    files = glob.glob(os.path.join(out_dir, "*.ts")) + glob.glob(os.path.join(out_dir, "*.mp4"))
    
    def safe_getctime(path):
        try:
            return os.path.getctime(path)
        except OSError:
            return 0
            
    if files:
        return max(files, key=safe_getctime)
    return None


def probe_stream_info(ts_path):
    """
    Probe a .ts segment to extract codec, resolution, and bitrate
    for the master.m3u8 stream info.
    Returns dict with codecs, resolution, bandwidth or None on failure.
    """
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            ts_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        fmt = data.get("format", {})

        video_codec = None
        audio_codec = None
        resolution = None

        for s in streams:
            if s.get("codec_type") == "video" and not video_codec:
                # Map codec_name to HLS codec string
                codec_name = s.get("codec_name", "")
                profile = s.get("profile", "").lower()
                level = s.get("level", 0)
                w = s.get("width", 0)
                h = s.get("height", 0)
                if w and h:
                    resolution = f"{w}x{h}"

                if "hevc" in codec_name or "h265" in codec_name or "265" in codec_name:
                    # HEVC codec string
                    video_codec = f"hev1.1.6.L{level}.90"
                elif "h264" in codec_name or "264" in codec_name:
                    # AVC codec string (approximate from profile/level)
                    profile_idc = "42" if "base" in profile else "4d" if "main" in profile else "64"
                    video_codec = f"avc1.{profile_idc}00{level:02x}"
                else:
                    video_codec = codec_name

            elif s.get("codec_type") == "audio" and not audio_codec:
                codec_name = s.get("codec_name", "")
                if "aac" in codec_name:
                    audio_codec = "mp4a.40.2"
                elif "ac3" in codec_name or "eac3" in codec_name or "ec-3" in codec_name:
                    audio_codec = "ec-3"
                elif "opus" in codec_name:
                    audio_codec = "opus"
                else:
                    audio_codec = codec_name

        # Estimate bandwidth from format bitrate or file size
        bitrate = int(fmt.get("bit_rate", 0))
        if not bitrate:
            # Estimate from file size and duration
            size = int(fmt.get("size", 0))
            duration = float(fmt.get("duration", 0))
            if size and duration:
                bitrate = int(size * 8 / duration)

        codecs_parts = [c for c in [video_codec, audio_codec] if c]
        return {
            "codecs": ",".join(codecs_parts) if codecs_parts else None,
            "resolution": resolution,
            "bandwidth": bitrate or 5000000,  # Default 5Mbps if unknown
        }
    except Exception as e:
        logger.warning(f"Failed to probe {ts_path}: {e}")
        return None


def create_master_playlist(out_dir, ts_path):
    """
    Create a master.m3u8 in the date directory that wraps playlist.m3u8
    with stream metadata. Makes recordings directly playable from HF storage.
    """
    master_path = os.path.join(out_dir, "master.m3u8")
    if os.path.exists(master_path):
        return  # Already created for today

    info = probe_stream_info(ts_path)

    # Build STREAM-INF line
    stream_inf_parts = []
    if info:
        stream_inf_parts.append(f"BANDWIDTH={info['bandwidth']}")
        if info.get("resolution"):
            stream_inf_parts.append(f"RESOLUTION={info['resolution']}")
        if info.get("codecs"):
            stream_inf_parts.append(f'CODECS="{info["codecs"]}"')
    else:
        # Fallback defaults
        stream_inf_parts.append("BANDWIDTH=5000000")

    stream_inf = ",".join(stream_inf_parts)

    content = (
        "#EXTM3U\n"
        "\n"
        f"#EXT-X-STREAM-INF:{stream_inf}\n"
        "playlist.m3u8\n"
    )

    try:
        with open(master_path, 'w') as f:
            f.write(content)
        logger.info(f"[📋] Created master.m3u8: {stream_inf}")
    except OSError as e:
        logger.warning(f"Failed to write master.m3u8: {e}")


def generate_vod_playlist(out_dir, segment_duration):
    """
    Generate a VOD-compatible playlist.m3u8 from .ts segments on disk.
    Includes #EXT-X-PLAYLIST-TYPE:VOD and #EXT-X-ENDLIST so players
    treat it as a completed recording (seekable, not live).
    """
    ts_files = []
    try:
        for entry in os.scandir(out_dir):
            if not entry.is_file() or not entry.name.endswith('.ts'):
                continue
            if re.match(r'^\d{6}\.ts$', entry.name):
                ts_files.append(entry.name)
    except OSError:
        return

    if not ts_files:
        return

    ts_files.sort()

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{segment_duration}",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        "",
    ]

    for ts in ts_files:
        lines.append(f"#EXTINF:{segment_duration},")
        lines.append(ts)

    lines.append("")
    lines.append("#EXT-X-ENDLIST")

    playlist_path = os.path.join(out_dir, "playlist.m3u8")
    try:
        tmp_path = playlist_path + ".tmp"
        with open(tmp_path, 'w') as f:
            f.write("\n".join(lines) + "\n")
        os.rename(tmp_path, playlist_path)
    except OSError as e:
        logger.warning(f"Failed to write VOD playlist: {e}")


def start_camera(channel, rtsp_url, base_dir, segment_duration):
    """Record RTSP stream for a single camera channel."""
    proc = None
    consecutive_failures = 0
    last_file_check = 0
    last_playlist_regen = 0
    current_date = None
    master_created = False
    
    while True:
        # Get date-specific output directory
        out_dir = get_output_dir(base_dir, channel)
        ensure_dir(out_dir)
        
        # Check if date changed (midnight rollover)
        today = datetime.now().strftime("%Y-%m-%d")
        if current_date and current_date != today:
            # Generate final VOD playlist for the old date before switching
            old_dir = get_output_dir(base_dir, channel).replace(today, current_date)
            generate_vod_playlist(old_dir, segment_duration)
            # Date changed, restart to use new folder
            if proc:
                proc.terminate()
                proc.wait()
                proc = None

                logger.info(f"[📅] CH{channel} date rollover, restarting")
            master_created = False  # Reset for new date
        current_date = today
        
        if is_stopped(channel):
            if proc:
                proc.terminate()
                proc.wait()
                proc = None

                logger.info(f"[⏹] CH{channel} stopped")
            consecutive_failures = 0
            time.sleep(2)
            continue
        
        if proc is None:
            logger.info(f"[▶] CH{channel} starting -> {out_dir}")

            # HLS output for time-scroll playback
            # Segments are immediately web-playable, no conversion needed
            cmd = [
                config.settings.ffmpeg_bin,
                "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-fflags", "+genpts+igndts+discardcorrupt",
                "-i", rtsp_url,
            ]

            # Inline Transcoding Logic
            if config.settings.inline_transcoding:
                # Use configured codec or default to libx265 if 'copy' is set
                v_codec = config.settings.video_codec if config.settings.video_codec != "copy" else "libx265"
                
                logger.info(f"[🎥] CH{channel} Inline Transcoding ENABLED: {v_codec} (CRF {config.settings.video_crf}, VF: {config.settings.ffmpeg_vf_args})")
                
                # 1. Hardware Init (Correct place: BEFORE -i)
                if config.settings.ffmpeg_hw_args:
                     # Insert HW args at the beginning (after binary) to act as global options
                     hw_args = config.settings.ffmpeg_hw_args.split()
                     for arg in reversed(hw_args):
                         cmd.insert(1, arg)
                
                # 2. Video Filters (AFTER -i, BEFORE Codec)
                if config.settings.ffmpeg_vf_args:
                     cmd.extend(["-vf", config.settings.ffmpeg_vf_args])

                cmd.extend(["-c:v", v_codec])

                # Logic for Quality: CRF vs QP
                # If using VAAPI/QSV, mapped "video_crf" to "-qp" usually
                is_vaapi = "vaapi" in v_codec or "qsv" in v_codec
                if is_vaapi:
                    cmd.extend(["-rc_mode", "CQP"])
                    cmd.extend(["-qp", str(config.settings.video_crf)])
                else:
                    cmd.extend(["-crf", str(config.settings.video_crf)])
                    cmd.extend(["-preset", config.settings.video_preset])
                
                # Audio: Force copy for inline VAAPI to keep it simple/fast
                cmd.extend(["-c:a", "aac"])

                # Force keyframes at segment boundaries
                cmd.extend(["-force_key_frames", f"expr:gte(t,n_forced*{segment_duration})"])
            else:
                cmd.extend(["-c:v", "copy"])
                cmd.extend(["-c:a", "aac"])

            cmd.extend([
                "-f", "hls",
                "-hls_time", str(segment_duration),
                "-hls_list_size", "0",  # Keep all segments in playlist
                "-hls_flags", "append_list+program_date_time",
                "-strftime", "1",
                "-hls_segment_filename", f"{out_dir}/%H%M%S.ts",
                f"{out_dir}/_live.m3u8"
            ])

            # Log the full command for debugging
            logger.info(f"[🐛] Full FFmpeg command:\n{' '.join(cmd)}")

            try:
                proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
                consecutive_failures = 0
                last_file_check = time.time()
            except Exception as e:
                logger.error(f"[❌] CH{channel} failed to start: {e}")
                time.sleep(2)
                continue
        
        # Check if process is still running
        ret = proc.poll()
        if ret is not None:
            # Capture error logs from ffmpeg
            if proc.stderr:
                err_output = proc.stderr.read().decode('utf-8', errors='ignore')
                if err_output:
                     logger.error(f"[❌] CH{channel} FFmpeg Crash Log:\n{err_output[-1000:]}")  # Last 1000 chars

            consecutive_failures += 1
            delay = 2 if consecutive_failures < 5 else min(consecutive_failures * 2, 30)
            logger.warning(f"[⚠] CH{channel} crashed (code {ret}), restart in {delay}s")
            proc = None
            time.sleep(delay)
        else:
            # Every 10 seconds, check if our output file still exists 
            # (or if we just converted it, that counts as existing)
            if time.time() - last_file_check > 10:
                last_file_check = time.time()
                latest = get_latest_file(out_dir, channel)
                
                # If no MKV or MP4 exists for today, and we've been running for > segment time, something is wrong
                # NOTE: We check against recording_start_time, not last_file_check
                if latest is None:
                    # Give a reasonable grace period (2x segment duration) before declaring failure
                    # This handles slow starts and network issues
                    logger.warning(f"[🔄] CH{channel} no output files found, restarting...")
                    proc.terminate()
                    proc.wait()
                    proc = None
                    continue
                
                # Create master.m3u8 once after first segment is available
                if not master_created and latest and latest.endswith('.ts'):
                    create_master_playlist(out_dir, latest)
                    master_created = True

                # Regenerate VOD playlist every 5 minutes (not every check)
                if latest and latest.endswith('.ts') and (time.time() - last_playlist_regen > 300):
                    generate_vod_playlist(out_dir, segment_duration)
                    last_playlist_regen = time.time()
            time.sleep(1)


def main():
    try:
        # Use config module if env vars are missing, or strict check
        if not config.settings.dvr_ip: raise EnvironmentError("DVR_IP not set")
        if not config.settings.dvr_user: raise EnvironmentError("DVR_USER not set")
    except EnvironmentError as e:
        logger.error(f"[❌] {e}")
        return

    ensure_dir(config.settings.record_dir)
    

    logger.info(f"[✓] DVR: {config.settings.dvr_ip}:{config.settings.dvr_port}")
    logger.info(f"[✓] Channels: {config.settings.num_channels}")
    logger.info(f"[✓] Segment: {config.settings.segment_duration}s")
    logger.info(f"[✓] Output: {config.settings.record_dir}/ch{{N}}/{{date}}/")
    logger.info(f"[✓] Source: go2rtc relay (localhost:{config.settings.go2rtc_rtsp_port})")

    # --- Start Recording Threads ---
    # Using go2rtc relay as unified RTSP source (single DVR connection)
    threads = []
    for ch in config.settings.get_active_channels():
        # Use go2rtc as RTSP source for unified architecture
        rtsp_url = build_go2rtc_url(ch)
        t = threading.Thread(
            target=start_camera, 
            args=(ch, rtsp_url, config.settings.record_dir, config.settings.segment_duration),
            daemon=True
        )
        t.start()
        threads.append(t)
        logger.info(f"[✓] CH{ch} recording thread started")

    while True:
        time.sleep(60)
        ensure_dir(config.settings.record_dir)


if __name__ == "__main__":
    main()
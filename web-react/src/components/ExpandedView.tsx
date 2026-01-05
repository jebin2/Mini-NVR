import { useState, useEffect, useMemo } from 'react'
import { Channel, fetchDates } from '../services/api'
import { getHlsApiUrl, getJellyJumpUrl } from '../services/go2rtc'
import TimeScroller from './TimeScroller'
import './ExpandedView.css'

interface ExpandedViewProps {
    camId: string
    channels: Record<string, Channel>
}

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [hlsUrl, setHlsUrl] = useState<string | null>(null)

    useEffect(() => {
        loadDates()
    }, [camId])

    async function loadDates() {
        try {
            const data = await fetchDates(camId)
            setDates(data.dates || [])
            if (data.dates?.length > 0) {
                setSelectedDate(data.dates[0])
            }
        } catch (err) {
            console.error('Failed to load dates:', err)
        }
    }

    // Raw video.currentTime from player (not wall-clock adjusted)
    const [videoTime, setVideoTime] = useState<number | null>(null)

    // Helper to parse HH:MM:SS to seconds
    function parseTime(timeStr: string): number {
        const parts = timeStr.split(':')
        return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
    }

    // Calculate playlist start time from the HLS URL (wall-clock seconds)
    const playlistStart = useMemo(() => {
        if (!hlsUrl) return null
        try {
            const urlObj = new URL(hlsUrl)
            const videoUrl = urlObj.searchParams.get('video_url')
            if (!videoUrl) return null

            // Handle relative video_url (prepend origin if needed)
            const fullVideoUrl = videoUrl.startsWith('/')
                ? window.location.origin + videoUrl
                : videoUrl

            const vUrlObj = new URL(fullVideoUrl)
            const start = vUrlObj.searchParams.get('start')
            if (start) {
                return parseTime(start)
            }
        } catch (e) {
            console.warn("Failed to parse start time from URL", e)
        }
        return null
    }, [hlsUrl])

    // Reset video time when playing new URL
    useEffect(() => {
        setVideoTime(null)
    }, [hlsUrl])

    // Listen for timeupdate and streamError messages from JellyJump player
    const [streamError, setStreamError] = useState<{ title: string; message: string } | null>(null)

    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            // Security check: ensure message comes from expected player origin
            const allowedOrigins = [window.location.origin, "https://www.voidall.com", "https://cctv.voidall.com"]
            if (!allowedOrigins.includes(event.origin)) return;

            if (event.data && event.data.type === 'timeupdate') {
                if (typeof event.data.currentTime === 'number') {
                    // Store raw video time - TimeScroller will map to actual segment time
                    setVideoTime(event.data.currentTime)
                }
                // Clear any previous error on successful playback
                if (streamError) setStreamError(null)
            }

            // Handle stream error from JellyJump
            if (event.data && event.data.type === 'streamError') {
                console.warn('[ExpandedView] Stream error from player:', event.data.error)
                setStreamError({
                    title: event.data.error?.title || 'Stream Error',
                    message: event.data.error?.message || 'Failed to load stream'
                })
            }
        }

        window.addEventListener('message', handleMessage)
        return () => window.removeEventListener('message', handleMessage)
    }, [streamError])

    function playLive() {
        setHlsUrl(null)
        setVideoTime(null)
        setStreamError(null) // Clear any previous error
        // Switch to today/latest date when going live
        if (dates.length > 0) {
            setSelectedDate(dates[0])
        }
    }

    // Force refresh the player to retry after error
    const [retryKey, setRetryKey] = useState(0)
    function retryStream() {
        setStreamError(null)
        setRetryKey(prev => prev + 1)
    }

    // Handler for TimeScroller - plays HLS at a specific time
    function handlePlayHls(url: string) {
        setHlsUrl(url)
    }

    function getVideoSrc(): string {
        // If playing from TimeScroller
        if (hlsUrl) {
            return hlsUrl
        }

        // Default: go2rtc WebRTC stream for LIVE
        // Use JellyJump (HLS) for live view (Unified Player)
        return getJellyJumpUrl(getHlsApiUrl(camId))
    }

    const videoSrc = getVideoSrc()
    const isLive = !hlsUrl

    return (
        <div className="expanded-view">
            <div className="player-header">
                <h2>Camera {camId}</h2>
            </div>

            <div className="video-stage">
                {videoSrc ? (
                    <iframe
                        key={`${videoSrc}-${retryKey}`}
                        src={videoSrc}
                        allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
                        className="video-player"
                    />
                ) : (
                    <div className="video-placeholder">Select a recording</div>
                )}

                {/* Stream Error Overlay with Retry Button */}
                {streamError && (
                    <div className="stream-error-overlay">
                        <div className="stream-error-content">
                            <span className="stream-error-icon">⚠️</span>
                            <h3>{streamError.title}</h3>
                            <p>{streamError.message}</p>
                            <button className="stream-error-retry-btn" onClick={retryStream}>
                                🔄 Retry
                            </button>
                            <button className="stream-error-live-btn" onClick={playLive}>
                                📺 Go Live
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Time Scroller for HLS seeking */}
            {selectedDate && (
                <TimeScroller
                    camId={camId}
                    date={selectedDate}
                    availableDates={dates}
                    onDateChange={setSelectedDate}
                    isLive={isLive}
                    videoTime={videoTime}
                    playlistStart={playlistStart}
                    onPlayHls={handlePlayHls}
                    onPlayLive={playLive}
                />
            )}
        </div>
    )
}

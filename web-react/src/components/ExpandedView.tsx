import { useState, useEffect, useMemo } from 'react'
import { Channel, fetchDates } from '../services/api'
import { getWebRTCUrl } from '../services/go2rtc'
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

    const [playbackTime, setPlaybackTime] = useState<number | null>(null)

    // Helper to parse HH:MM:SS to seconds
    function parseTime(timeStr: string): number {
        const parts = timeStr.split(':')
        return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
    }

    // Calculate start time offset from the HLS URL
    // URL format: .../embed.html?video_url=.../playlist.m3u8?start=HH:MM:SS
    const startTimeOffset = useMemo(() => {
        if (!hlsUrl) return 0
        try {
            const urlObj = new URL(hlsUrl)
            const videoUrl = urlObj.searchParams.get('video_url')
            if (!videoUrl) return 0

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
        return 0
    }, [hlsUrl])

    // Reset playback time when playing new URL
    useEffect(() => {
        setPlaybackTime(null)
    }, [hlsUrl])

    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            // Security check: ensure message comes from expected player origin
            // Allow voidall.com and same origin
            const allowedOrigins = [window.location.origin, "https://www.voidall.com", "https://cctv.voidall.com"]
            if (!allowedOrigins.includes(event.origin)) return;

            if (event.data && event.data.type === 'timeupdate') {
                if (typeof event.data.currentTime === 'number') {
                    // Add offset to relative time
                    setPlaybackTime(startTimeOffset + event.data.currentTime)
                }
            }
        }

        window.addEventListener('message', handleMessage)
        return () => window.removeEventListener('message', handleMessage)
    }, [startTimeOffset])

    function playLive() {
        setHlsUrl(null)
        setPlaybackTime(null)
        // Switch to today/latest date when going live
        if (dates.length > 0) {
            setSelectedDate(dates[0])
        }
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
        return getWebRTCUrl(camId)
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
                        src={videoSrc}
                        allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
                        className="video-player"
                    />
                ) : (
                    <div className="video-placeholder">Select a recording</div>
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
                    playbackTime={playbackTime}
                    onPlayHls={handlePlayHls}
                    onPlayLive={playLive}
                />
            )}
        </div>
    )
}

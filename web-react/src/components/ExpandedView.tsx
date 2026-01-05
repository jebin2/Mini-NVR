import { useState, useEffect, useMemo } from 'react'
import { Channel, fetchDates, getPlaylistUrl } from '../services/api'
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
    const [playMode, setPlayMode] = useState<'live' | 'buffer'>('buffer')

    // Gap State
    const [gapState, setGapState] = useState<{ isGap: boolean; nextTime: number | null }>({ isGap: false, nextTime: null })
    const [forceTime, setForceTime] = useState<number | null>(null)

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
            // Start with 30s buffer mode by default
            setTimeout(() => play30sBuffer(), 100)
        } catch (err) {
            console.error('Failed to load dates:', err)
        }
    }

    const [videoTime, setVideoTime] = useState<number | null>(null)

    function parseTime(timeStr: string): number {
        const parts = timeStr.split(':')
        return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
    }

    function formatTimeHMS(seconds: number): string {
        const h = Math.floor(seconds / 3600)
        const m = Math.floor((seconds % 3600) / 60)
        const s = Math.floor(seconds % 60)
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }

    const playlistStart = useMemo(() => {
        if (!hlsUrl) return null
        try {
            const urlObj = new URL(hlsUrl)
            const videoUrl = urlObj.searchParams.get('video_url')
            if (!videoUrl) return null

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

    useEffect(() => {
        setVideoTime(null)
    }, [hlsUrl])

    const [streamError, setStreamError] = useState<{ title: string; message: string } | null>(null)

    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            const allowedOrigins = [window.location.origin, "https://www.voidall.com", "https://cctv.voidall.com"]
            if (!allowedOrigins.includes(event.origin)) return;

            if (event.data && event.data.type === 'timeupdate') {
                if (typeof event.data.currentTime === 'number') {
                    setVideoTime(event.data.currentTime)
                }
                if (streamError) setStreamError(null)
            }

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
        setStreamError(null)
        setForceTime(null)
        setPlayMode('live')
        setGapState({ isGap: false, nextTime: null })
        if (dates.length > 0) {
            setSelectedDate(dates[0])
        }
    }

    function play30sBuffer() {
        const now = new Date()
        const today = now.toISOString().split('T')[0]
        const thirtySecondsAgo = new Date(now.getTime() - 30000)
        const startSeconds = thirtySecondsAgo.getHours() * 3600 +
            thirtySecondsAgo.getMinutes() * 60 +
            thirtySecondsAgo.getSeconds()
        const startTime = formatTimeHMS(startSeconds)

        const url = getPlaylistUrl(camId, today, startTime)
        setHlsUrl(getJellyJumpUrl(window.location.origin + url))
        setSelectedDate(today)
        setPlayMode('buffer')
        setStreamError(null)
        setForceTime(null)
    }

    function handleModeChange(mode: 'live' | 'buffer') {
        if (mode === 'live') {
            playLive()
        } else {
            play30sBuffer()
        }
    }

    const [retryKey, setRetryKey] = useState(0)
    function retryStream() {
        setStreamError(null)
        setRetryKey(prev => prev + 1)
    }

    function handlePlayHls(url: string) {
        setHlsUrl(url)
        setPlayMode('buffer')
        setStreamError(null)
        setForceTime(null) // Clear force time once we play
    }

    function handleGoToNext() {
        if (gapState.nextTime !== null) {
            // Set forceTime to trigger TimeScroller jump
            setForceTime(gapState.nextTime)
        }
    }

    function getVideoSrc(): string {
        if (hlsUrl) {
            return hlsUrl
        }
        return getJellyJumpUrl(getHlsApiUrl(camId))
    }

    const videoSrc = getVideoSrc()
    const isLive = playMode === 'live' && !hlsUrl

    // Determining if we should show the player or placeholder
    const showPlayer = !streamError && !gapState.isGap

    // Explicitly unmount iframe if gap or error
    // For error, we show overlay on top of placeholder? 
    // Or just placeholder.
    // Spec: "for network error... show the same 1) display by removing iframe with goto next available segm"

    return (
        <div className="expanded-view">
            <div className="video-stage">
                <div className="camera-badge">📹 CH{camId}</div>

                {showPlayer ? (
                    <iframe
                        key={`${videoSrc}-${retryKey}`}
                        src={videoSrc}
                        allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
                        className="video-player"
                    />
                ) : (
                    <div className="no-video-placeholder">
                        <div className="placeholder-content">
                            <span className="placeholder-icon">🚫</span>
                            <h3>Video Not Available</h3>
                            <p>No recording found at this time.</p>

                            {gapState.nextTime !== null && (
                                <button className="placeholder-btn" onClick={handleGoToNext}>
                                    ⏭ Go to Next ({formatTimeHMS(gapState.nextTime)})
                                </button>
                            )}

                            {/* If it's a stream error, maybe show retry too? */}
                            {streamError && (
                                <div className="error-details">
                                    <p className="error-msg">{streamError.message}</p>
                                    <button className="placeholder-retry-btn" onClick={retryStream}>🔄 Retry</button>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

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
                    playMode={playMode}
                    onModeChange={handleModeChange}
                    onGapChange={(isGap, nextTime) => setGapState({ isGap, nextTime })}
                    externalForceTime={forceTime}
                />
            )}
        </div>
    )
}

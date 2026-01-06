import { useState, useEffect } from 'react'
import { Channel, Segment, fetchDates, fetchSegments, getPlaylistUrl } from '../services/api'
import { getHlsApiUrl, getJellyJumpUrl } from '../services/go2rtc'
import { getLocalDateString } from '../utils/dateUtils'
import VideoPlayer from './VideoPlayer'
import InfoOverlay from './InfoOverlay'
import TimeScroller from './TimeScroller'
import './ExpandedView.css'

interface ExpandedViewProps {
    camId: string
    channels: Record<string, Channel>
}

// Helper to parse time string to seconds
function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

// Find segment containing the given time
function findSegmentAt(time: number, segments: Segment[]): Segment | null {
    return segments.find(seg => {
        const start = parseTime(seg.time)
        return time >= start && time < start + seg.duration
    }) || null
}

// Simple state machine for video area
type VideoAreaState =
    | { type: 'live' }
    | { type: 'loading' }
    | { type: 'playing'; url: string; segmentStartTime: number }
    | { type: 'no-video'; nextTime: number | null }

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [forceTime, setForceTime] = useState<number | null>(null)
    const [segments, setSegments] = useState<Segment[]>([])

    // Simple state machine - one source of truth
    const [videoState, setVideoState] = useState<VideoAreaState>({ type: 'live' })

    // Video playback time (from VideoPlayer)
    const [playerTime, setPlayerTime] = useState<number | null>(null)

    // === LOAD DATES ===
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

    // === LOAD SEGMENTS ===
    const [hasAutoStarted, setHasAutoStarted] = useState(false)

    useEffect(() => {
        if (!selectedDate) return

        let isMounted = true

        async function load() {
            try {
                const data = await fetchSegments(camId, selectedDate)
                if (isMounted) {
                    const segs = data.segments || []
                    setSegments(segs)

                    // Auto-start 30s before current time on first load
                    if (!hasAutoStarted && segs.length > 0) {
                        setHasAutoStarted(true)
                        startLivePlayback(segs)
                    }
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                if (isMounted) setSegments([])
            }
        }

        load()

        // Refresh every 15s if today
        const today = getLocalDateString(new Date())
        let intervalId: number | null = null
        if (selectedDate === today) {
            intervalId = window.setInterval(load, 15000)
        }

        return () => {
            isMounted = false
            if (intervalId) clearInterval(intervalId)
        }
    }, [camId, selectedDate])

    // Start playback 30s before current time
    function startLivePlayback(segs: Segment[]) {
        const now = new Date()
        const thirtySecsAgo = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() - 30

        const segment = findSegmentAt(thirtySecsAgo, segs)
        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            const url = getPlaylistUrl(camId, selectedDate, segment.time)
            setVideoState({
                type: 'playing',
                url: getJellyJumpUrl(window.location.origin + url),
                segmentStartTime
            })
            setForceTime(thirtySecsAgo)
        }
    }

    // === HANDLERS ===

    function handleScrollStart() {
        // User started scrolling → unmount video player, show loading
        setVideoState({ type: 'loading' })
        setPlayerTime(null)
    }

    function handleScrollEnd(time: number) {
        // Find segment at user's selected time
        const segment = findSegmentAt(time, segments)

        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            const url = getPlaylistUrl(camId, selectedDate, segment.time)

            setVideoState({
                type: 'playing',
                url: getJellyJumpUrl(window.location.origin + url),
                segmentStartTime
            })
            setPlayerTime(null)  // Will be updated by VideoPlayer
        } else {
            // No video at this time
            // Find next available segment
            const nextSeg = segments.find(seg => parseTime(seg.time) > time)
            setVideoState({
                type: 'no-video',
                nextTime: nextSeg ? parseTime(nextSeg.time) : null
            })
        }
    }

    function handleVideoTimeUpdate(time: number) {
        setPlayerTime(time)
    }

    function handleDateChange(date: string) {
        setSelectedDate(date)
        setVideoState({ type: 'loading' })
        setPlayerTime(null)
    }

    function handleGoLive() {
        // "Live" means 30 seconds before current time (true live is slow)
        const now = new Date()
        const today = getLocalDateString(now)
        const thirtySecsAgo = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() - 30

        setSelectedDate(today)
        setPlayerTime(null)

        // Trigger playback at 30s ago
        const segment = findSegmentAt(thirtySecsAgo, segments)
        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            const url = getPlaylistUrl(camId, today, segment.time)
            setVideoState({
                type: 'playing',
                url: getJellyJumpUrl(window.location.origin + url),
                segmentStartTime
            })
            // Force TimeScroller to jump to this time
            setForceTime(thirtySecsAgo)
        } else {
            // No segment 30s ago, fallback to loading
            setVideoState({ type: 'loading' })
            setForceTime(thirtySecsAgo)
        }
    }

    function handleGoNext() {
        if (videoState.type === 'no-video' && videoState.nextTime !== null) {
            setForceTime(videoState.nextTime)
        }
    }

    // === RENDER HELPERS ===

    function formatTimeHMS(seconds: number): string {
        const h = Math.floor(seconds / 3600)
        const m = Math.floor((seconds % 3600) / 60)
        const s = Math.floor(seconds % 60)
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }

    function getLiveUrl(): string {
        return getJellyJumpUrl(getHlsApiUrl(camId))
    }

    // Get segmentStartTime for TimeScroller (only when playing)
    const segmentStartTime = videoState.type === 'playing' ? videoState.segmentStartTime : null

    // === RENDER ===

    return (
        <div className="expanded-view">
            <div className="video-stage">
                <div className="camera-badge">📹 CH{camId}</div>

                {/* State Machine Rendering */}
                {videoState.type === 'live' && (
                    <VideoPlayer url={getLiveUrl()} />
                )}

                {videoState.type === 'playing' && (
                    <VideoPlayer
                        url={videoState.url}
                        onTimeUpdate={handleVideoTimeUpdate}
                    />
                )}

                {videoState.type === 'loading' && (
                    <InfoOverlay type="loading" message="Loading video..." />
                )}

                {videoState.type === 'no-video' && (
                    <InfoOverlay
                        type="no-video"
                        onGoNext={videoState.nextTime ? handleGoNext : undefined}
                        nextTime={videoState.nextTime ? formatTimeHMS(videoState.nextTime) : null}
                        onGoLive={handleGoLive}
                    />
                )}
            </div>

            {selectedDate && (
                <TimeScroller
                    camId={camId}
                    date={selectedDate}
                    availableDates={dates}
                    onDateChange={handleDateChange}
                    onScrollStart={handleScrollStart}
                    onScrollEnd={handleScrollEnd}
                    externalForceTime={forceTime}
                    segmentStartTime={segmentStartTime}
                    playerTime={playerTime}
                />
            )}

            {/* Mode toggle */}
            <div className="mode-controls">
                <button
                    className={`mode-btn ${videoState.type === 'live' ? 'active' : ''}`}
                    onClick={handleGoLive}
                >
                    Live
                </button>
            </div>
        </div>
    )
}

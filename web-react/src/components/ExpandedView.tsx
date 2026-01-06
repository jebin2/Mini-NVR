import { useState, useEffect, useCallback } from 'react'
import { Channel, Segment, fetchDates, fetchSegments, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl } from '../services/go2rtc'
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

// Get time 30 seconds before now
function getThirtySecsAgo(): number {
    const now = new Date()
    return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() - 30
}

// Simple state machine for video area
type VideoAreaState =
    | { type: 'loading' }
    | { type: 'playing'; url: string; segmentStartTime: number }
    | { type: 'no-video'; nextTime: number | null }

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [forceTime, setForceTime] = useState<number | null>(null)
    const [segments, setSegments] = useState<Segment[]>([])
    const [hasAutoStarted, setHasAutoStarted] = useState(false)

    // Simple state machine - one source of truth
    const [videoState, setVideoState] = useState<VideoAreaState>({ type: 'loading' })

    // Video playback time (from VideoPlayer)
    const [playerTime, setPlayerTime] = useState<number | null>(null)

    // === COMMON: Go to "Live" (30s before current time) ===
    const goToLive = useCallback((segs?: Segment[]) => {
        const today = getLocalDateString(new Date())
        const time = getThirtySecsAgo()
        const segsToUse = segs || segments

        // Ensure we're on today's date
        if (selectedDate !== today) {
            setSelectedDate(today)
        }

        setPlayerTime(null)

        const segment = findSegmentAt(time, segsToUse)
        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            const url = getPlaylistUrl(camId, today, segment.time)
            setVideoState({
                type: 'playing',
                url: getJellyJumpUrl(window.location.origin + url),
                segmentStartTime
            })
            setForceTime(time)
        } else {
            // No segment at 30s ago
            const nextSeg = segsToUse.find(seg => parseTime(seg.time) > time)
            setVideoState({
                type: 'no-video',
                nextTime: nextSeg ? parseTime(nextSeg.time) : null
            })
            setForceTime(time)
        }
    }, [camId, segments, selectedDate])

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
    useEffect(() => {
        if (!selectedDate) return

        let isMounted = true

        async function load() {
            try {
                const data = await fetchSegments(camId, selectedDate)
                if (isMounted) {
                    const segs = data.segments || []
                    setSegments(segs)

                    // Auto-start 30s playback on first load
                    if (!hasAutoStarted && segs.length > 0) {
                        setHasAutoStarted(true)
                        goToLive(segs)
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
    }, [camId, selectedDate, hasAutoStarted, goToLive])

    // === HANDLERS ===

    function handleScrollStart() {
        setVideoState({ type: 'loading' })
        setPlayerTime(null)
    }

    function handleScrollEnd(time: number) {
        const segment = findSegmentAt(time, segments)

        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            const url = getPlaylistUrl(camId, selectedDate, segment.time)
            setVideoState({
                type: 'playing',
                url: getJellyJumpUrl(window.location.origin + url),
                segmentStartTime
            })
            setPlayerTime(null)
        } else {
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

    const segmentStartTime = videoState.type === 'playing' ? videoState.segmentStartTime : null

    // === RENDER ===

    return (
        <div className="expanded-view">
            <div className="video-stage">
                <div className="camera-badge">📹 CH{camId}</div>

                {/* State Machine Rendering */}
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
                        onGoLive={() => goToLive()}
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
                    className={`mode-btn ${videoState.type === 'playing' ? 'active' : ''}`}
                    onClick={() => goToLive()}
                >
                    Live
                </button>
            </div>
        </div>
    )
}

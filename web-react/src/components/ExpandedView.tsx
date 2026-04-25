import { useState, useEffect, useCallback, useRef } from 'react'
import { Channel, Segment, fetchDates, fetchSegments, fetchConfig, getHfPlaylistUrl, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl, getJellyJumpHfUrl } from '../services/go2rtc'
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
    const [hfBucketUrl, setHfBucketUrl] = useState('')

    // Simple state machine - one source of truth
    const [videoState, setVideoState] = useState<VideoAreaState>({ type: 'loading' })

    // Video playback time (from VideoPlayer)
    const [playerTime, setPlayerTime] = useState<number | null>(null)

    // Load HF bucket URL from config
    useEffect(() => {
        fetchConfig().then(cfg => {
            setHfBucketUrl(cfg.hfBucketUrl || '')
        }).catch(() => {})
    }, [])

    /**
     * Build the playback URL for a given date and segment.
     * If HF bucket is configured, use HF CDN (full day VOD).
     * Otherwise fall back to NVR server API (time-specific playlist).
     */
    const buildPlaybackUrl = useCallback((date: string, segment?: Segment): string => {
        if (hfBucketUrl) {
            // HF CDN: full day VOD playlist — no NVR server involvement
            const hfUrl = getHfPlaylistUrl(hfBucketUrl, camId, date)
            return getJellyJumpHfUrl(hfUrl)
        } else {
            // Fallback: NVR server API (time-specific playlist)
            const url = getPlaylistUrl(camId, date, segment?.time)
            return getJellyJumpUrl(window.location.origin + url)
        }
    }, [hfBucketUrl, camId])

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
            setVideoState({
                type: 'playing',
                url: buildPlaybackUrl(today, segment),
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
    }, [camId, segments, selectedDate, buildPlaybackUrl])

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

    // Ref so the segments effect can always call the latest goToLive without
    // including it in the dependency array (which would create an infinite loop:
    // segments → goToLive ref changes → effect re-runs → setSegments → repeat).
    const goToLiveRef = useRef(goToLive)
    useEffect(() => { goToLiveRef.current = goToLive })

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
                        goToLiveRef.current(segs)
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
    }, [camId, selectedDate, hasAutoStarted])

    // === HANDLERS ===

    function handleScrollStart() {
        setVideoState({ type: 'loading' })
        setPlayerTime(null)
    }

    function handleScrollEnd(time: number) {
        const segment = findSegmentAt(time, segments)

        if (segment) {
            const segmentStartTime = parseTime(segment.time)
            setVideoState({
                type: 'playing',
                url: buildPlaybackUrl(selectedDate, segment),
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
                    onGoLive={() => goToLive()}
                    externalForceTime={forceTime}
                    segmentStartTime={segmentStartTime}
                    playerTime={playerTime}
                />
            )}
        </div>
    )
}

import { useState, useRef, useEffect, useCallback } from 'react'
import { Segment, fetchSegments, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl } from '../services/go2rtc'
import './TimeScroller.css'

interface TimeScrollerProps {
    camId: string
    date: string
    availableDates: string[]
    onDateChange: (date: string) => void
    isLive: boolean
    playbackTime?: number | null // Current playback time in seconds (for sync)
    onPlayHls: (url: string) => void
    onPlayLive: () => void
}

// Zoom levels in minutes
const ZOOM_LEVELS = [30, 60, 120, 240, 720, 1440] // 30min, 1hr, 2hr, 4hr, 12hr, 24hr
const DEFAULT_ZOOM_INDEX = 2 // 2 hours
const SECONDS_IN_DAY = 86400

function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

function formatTimeShort(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

function formatZoomLabel(minutes: number): string {
    if (minutes >= 1440) return '24h'
    if (minutes >= 60) return `${minutes / 60}h`
    return `${minutes}m`
}

/**
 * TimeScroller - Zoomable, scrollable timeline for HLS recordings
 * 
 * Features:
 * - Zoom: 30min to 24hr range
 * - Scroll: Horizontal scroll through day
 * - Seek: Tap/drag to select time
 * - Live: Scrubber syncs with current time in live mode
 */
export default function TimeScroller({ camId, date, availableDates, onDateChange, isLive, playbackTime, onPlayHls, onPlayLive }: TimeScrollerProps) {
    const [segments, setSegments] = useState<Segment[]>([])
    const [loading, setLoading] = useState(true)

    // Zoom state (index into ZOOM_LEVELS)
    const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
    const zoomMinutes = ZOOM_LEVELS[zoomIndex]

    // Viewport start time in seconds (0 = 00:00)
    const [viewportStart, setViewportStart] = useState(0)

    // Scrubber state
    const [scrubberTime, setScrubberTime] = useState<number | null>(null)
    const [isDragging, setIsDragging] = useState(false)

    const trackRef = useRef<HTMLDivElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    // Helper: Get current time of day in seconds
    const getCurrentTimeSeconds = () => {
        const now = new Date()
        return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    }

    // Effect: Sync scrubber with external playback time (e.g. from HLS player)
    useEffect(() => {
        if (!isLive && playbackTime !== null && playbackTime !== undefined && !isDragging) {
            setScrubberTime(playbackTime)

            // Auto-scroll if scrubber moves out of view
            const viewportEnd = viewportStart + (zoomMinutes * 60)
            if (playbackTime < viewportStart || playbackTime > viewportEnd) {
                // Center it
                setViewportStart(Math.max(0, playbackTime - (zoomMinutes * 60) / 2))
            }
        }
    }, [isLive, playbackTime, isDragging, zoomMinutes, viewportStart])

    // Effect: Live Mode Clock
    useEffect(() => {
        if (!isLive) return

        // Update scrubber to current time immediately
        const updateClock = () => {
            const nowSec = getCurrentTimeSeconds()
            setScrubberTime(nowSec)
            return nowSec
        }

        const nowSec = updateClock()

        // Center viewport on current time if we are not dragging
        // and if scrubber is out of view (or just initially)
        const viewportSeconds = zoomMinutes * 60
        const viewportEnd = viewportStart + viewportSeconds

        if (nowSec < viewportStart || nowSec > viewportEnd) {
            setViewportStart(Math.max(0, nowSec - viewportSeconds / 2))
        }

        // Timer to update every second
        const interval = setInterval(updateClock, 1000)

        return () => clearInterval(interval)
    }, [isLive, zoomMinutes]) // Only re-run if live state or zoom changes

    // Load segments (Initial + Polling)
    useEffect(() => {
        let isMounted = true
        let intervalId: number | null = null

        async function load() {
            setLoading(prev => prev || true) // Only set loading true on initial
            try {
                const data = await fetchSegments(camId, date)
                if (!isMounted) return

                setSegments(data.segments)

                // If NOT live, center on latest recording (only on first load)
                if (!isLive && data.segments.length > 0 && loading) {
                    const lastSeg = data.segments[data.segments.length - 1]
                    const lastTime = parseTime(lastSeg.time)
                    const zoomSec = zoomMinutes * 60
                    setViewportStart(Math.max(0, lastTime - zoomSec / 2))
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                if (isMounted) setSegments([])
            }
            if (isMounted) setLoading(false)
        }

        load()

        // Poll every 15 seconds if viewing today (simple check: if date matches local date)
        const today = new Date().toISOString().split('T')[0]
        if (date === today) {
            intervalId = window.setInterval(load, 15000)
        }

        return () => {
            isMounted = false
            if (intervalId) clearInterval(intervalId)
        }
    }, [camId, date])

    // Clamp viewport when zoom changes
    useEffect(() => {
        const maxStart = SECONDS_IN_DAY - (zoomMinutes * 60)
        if (viewportStart > maxStart) {
            setViewportStart(Math.max(0, maxStart))
        }
    }, [zoomMinutes, viewportStart])

    // Calculate viewport in seconds
    const viewportSeconds = zoomMinutes * 60
    const viewportEnd = Math.min(viewportStart + viewportSeconds, SECONDS_IN_DAY)

    // Convert position to time
    const getTimeFromX = useCallback((clientX: number): number => {
        if (!trackRef.current) return viewportStart
        const rect = trackRef.current.getBoundingClientRect()
        const x = Math.max(0, Math.min(clientX - rect.left, rect.width))
        const pct = x / rect.width
        return Math.floor(viewportStart + pct * viewportSeconds)
    }, [viewportStart, viewportSeconds])

    // Zoom handlers
    const zoomIn = () => setZoomIndex(i => Math.max(0, i - 1))
    const zoomOut = () => setZoomIndex(i => Math.min(ZOOM_LEVELS.length - 1, i + 1))

    // Scroll handlers
    const scrollLeft = () => {
        const step = viewportSeconds / 2
        setViewportStart(v => Math.max(0, v - step))
    }
    const scrollRight = () => {
        const step = viewportSeconds / 2
        const maxStart = SECONDS_IN_DAY - viewportSeconds
        setViewportStart(v => Math.min(maxStart, v + step))
    }

    // Pointer handlers
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        setIsDragging(true)
        setScrubberTime(getTimeFromX(e.clientX))
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)
    }, [getTimeFromX])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging) return
        setScrubberTime(getTimeFromX(e.clientX))
    }, [isDragging, getTimeFromX])

    const handlePointerUp = useCallback(() => {
        if (!isDragging || scrubberTime === null) return
        setIsDragging(false)

        // Find segment at this time
        let found: Segment | null = null
        for (const seg of segments) {
            const start = parseTime(seg.time)
            const end = start + seg.duration
            if (scrubberTime >= start && scrubberTime < end) {
                found = seg
                break
            }
        }

        if (found) {
            const url = getPlaylistUrl(camId, date, found.time)
            onPlayHls(getJellyJumpUrl(window.location.origin + url))
        }
    }, [isDragging, scrubberTime, segments, camId, date, onPlayHls])

    // Build visible coverage blocks
    const coverageBlocks = (() => {
        if (segments.length === 0) return []

        // 1. Merge adjacent segments
        const merged: { start: number; end: number }[] = []

        let currentStart = parseTime(segments[0].time)
        let currentEnd = currentStart + segments[0].duration

        for (let i = 1; i < segments.length; i++) {
            const segStart = parseTime(segments[i].time)
            const segEnd = segStart + segments[i].duration

            // If gap is less than 2 seconds, merge
            if (segStart - currentEnd < 2) {
                currentEnd = Math.max(currentEnd, segEnd)
            } else {
                merged.push({ start: currentStart, end: currentEnd })
                currentStart = segStart
                currentEnd = segEnd
            }
        }
        merged.push({ start: currentStart, end: currentEnd })

        // 2. Map to visual blocks
        return merged.map(block => {
            // Skip if outside viewport
            if (block.end < viewportStart || block.start > viewportEnd) return null

            // Clamp to viewport
            const visStart = Math.max(block.start, viewportStart)
            const visEnd = Math.min(block.end, viewportEnd)

            const leftPct = ((visStart - viewportStart) / viewportSeconds) * 100
            const widthPct = ((visEnd - visStart) / viewportSeconds) * 100

            return { leftPct, widthPct }
        }).filter(Boolean) as { leftPct: number; widthPct: number }[]
    })()

    // Generate time markers
    const generateMarkers = () => {
        const markers: { pct: number; label: string }[] = []

        // Determine interval based on zoom
        let intervalMin = 30
        if (zoomMinutes <= 60) intervalMin = 10
        else if (zoomMinutes <= 120) intervalMin = 15
        else if (zoomMinutes <= 240) intervalMin = 30
        else if (zoomMinutes <= 720) intervalMin = 60
        else intervalMin = 120

        const intervalSec = intervalMin * 60
        const startMarker = Math.ceil(viewportStart / intervalSec) * intervalSec

        for (let t = startMarker; t <= viewportEnd; t += intervalSec) {
            const pct = ((t - viewportStart) / viewportSeconds) * 100
            const h = Math.floor(t / 3600)
            const m = Math.floor((t % 3600) / 60)
            markers.push({ pct, label: `${h}:${m.toString().padStart(2, '0')}` })
        }

        return markers
    }

    const markers = generateMarkers()
    const hasSegments = segments.length > 0

    return (
        <div className="time-scroller" ref={containerRef}>
            {/* Header: Date + Time + Live button */}
            <div className="scroller-header">
                <div className="header-left">
                    {/* Date Selector Pill */}
                    <div className="date-select-wrapper">
                        <select
                            className="date-select"
                            value={date}
                            onChange={(e) => onDateChange(e.target.value)}
                        >
                            {availableDates.map(d => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                        <span className="date-icon">📅</span>
                    </div>

                    <div className="time-display">
                        {scrubberTime !== null ? (
                            <span className="current-time">{formatTimeShort(scrubberTime)}</span>
                        ) : (
                            <span className="viewport-range">
                                {formatTimeShort(viewportStart)} - {formatTimeShort(viewportEnd)}
                            </span>
                        )}
                    </div>
                </div>
                {/* Only show Live button if NOT already in live mode */}
                {!isLive && (
                    <button className="btn-live-pill" onClick={onPlayLive}>
                        🔴 Live
                    </button>
                )}
                {isLive && (
                    <span className="live-badge">LIVE VIEW</span>
                )}
            </div>

            {/* Controls: Scroll + Zoom */}
            <div className="scroller-controls">
                <button className="nav-btn" onClick={scrollLeft} title="Earlier">◀</button>

                <div className="zoom-controls">
                    <button className="zoom-btn" onClick={zoomIn} disabled={zoomIndex === 0}>+</button>
                    <span className="zoom-label">{formatZoomLabel(zoomMinutes)}</span>
                    <button className="zoom-btn" onClick={zoomOut} disabled={zoomIndex === ZOOM_LEVELS.length - 1}>−</button>
                </div>

                <button className="nav-btn" onClick={scrollRight} title="Later">▶</button>
            </div>

            {/* Track */}
            <div
                ref={trackRef}
                className={`scroller-track ${isDragging ? 'active' : ''} ${loading ? 'loading' : ''}`}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
            >
                {/* Coverage blocks */}
                {coverageBlocks.map((block, i) => (
                    <div
                        key={i}
                        className="coverage-block"
                        style={{
                            left: `${block.leftPct}%`,
                            width: `${Math.max(block.widthPct, 0.5)}%`,
                        }}
                    />
                ))}

                {/* Scrubber */}
                {scrubberTime !== null && scrubberTime >= viewportStart && scrubberTime <= viewportEnd && (
                    <div
                        className="scrubber"
                        style={{ left: `${((scrubberTime - viewportStart) / viewportSeconds) * 100}%` }}
                    />
                )}

                {/* No recordings */}
                {!loading && !hasSegments && (
                    <div className="no-recordings">No recordings</div>
                )}
            </div>

            {/* Time markers */}
            <div className="time-markers">
                {markers.map((m, i) => (
                    <span key={i} style={{ left: `${m.pct}%` }}>{m.label}</span>
                ))}
            </div>
        </div>
    )
}

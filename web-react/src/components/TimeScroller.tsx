import { useState, useRef, useEffect, useCallback } from 'react'
import { Segment, fetchSegments, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl } from '../services/go2rtc'
import './TimeScroller.css'

interface TimeScrollerProps {
    camId: string
    date: string
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
 */
export default function TimeScroller({ camId, date, onPlayHls, onPlayLive }: TimeScrollerProps) {
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

    // Load segments
    useEffect(() => {
        async function load() {
            setLoading(true)
            try {
                const data = await fetchSegments(camId, date)
                setSegments(data.segments)

                // Auto-scroll to latest recording
                if (data.segments.length > 0) {
                    const lastSeg = data.segments[data.segments.length - 1]
                    const lastTime = parseTime(lastSeg.time)
                    // Center viewport on latest recording
                    const zoomSec = zoomMinutes * 60
                    setViewportStart(Math.max(0, lastTime - zoomSec / 2))
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                setSegments([])
            }
            setLoading(false)
        }
        load()
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
    const coverageBlocks = segments
        .map(seg => {
            const startSec = parseTime(seg.time)
            const endSec = startSec + seg.duration

            // Skip if outside viewport
            if (endSec < viewportStart || startSec > viewportEnd) return null

            // Clamp to viewport
            const visStart = Math.max(startSec, viewportStart)
            const visEnd = Math.min(endSec, viewportEnd)

            const leftPct = ((visStart - viewportStart) / viewportSeconds) * 100
            const widthPct = ((visEnd - visStart) / viewportSeconds) * 100

            return { leftPct, widthPct }
        })
        .filter(Boolean) as { leftPct: number; widthPct: number }[]

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
            {/* Header: Time display + Live button */}
            <div className="scroller-header">
                <div className="time-display">
                    {scrubberTime !== null ? (
                        <span className="current-time">{formatTimeShort(scrubberTime)}</span>
                    ) : (
                        <span className="viewport-range">
                            {formatTimeShort(viewportStart)} - {formatTimeShort(viewportEnd)}
                        </span>
                    )}
                </div>
                <button className="btn-live-pill" onClick={onPlayLive}>
                    🔴 Live
                </button>
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

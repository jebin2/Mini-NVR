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

const SECONDS_IN_DAY = 86400

function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

function formatTimeShort(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    // Mobile-friendly: just show HH:MM
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`
}

/**
 * TimeScroller - A touch-friendly draggable timeline for HLS recordings
 * Optimized for mobile with large touch targets and simple time display
 */
export default function TimeScroller({ camId, date, onPlayHls, onPlayLive }: TimeScrollerProps) {
    const [segments, setSegments] = useState<Segment[]>([])
    const [scrubberTime, setScrubberTime] = useState<number | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [loading, setLoading] = useState(true)
    const trackRef = useRef<HTMLDivElement>(null)

    // Load segments when date changes
    useEffect(() => {
        async function loadSegments() {
            setLoading(true)
            try {
                const data = await fetchSegments(camId, date)
                setSegments(data.segments)
            } catch (err) {
                console.error('Failed to load segments:', err)
                setSegments([])
            }
            setLoading(false)
        }
        loadSegments()
    }, [camId, date])

    // Convert touch/mouse position to time
    const getTimeFromEvent = useCallback((clientX: number): number => {
        if (!trackRef.current) return 0
        const rect = trackRef.current.getBoundingClientRect()
        const x = Math.max(0, Math.min(clientX - rect.left, rect.width))
        const pct = x / rect.width
        return Math.floor(pct * SECONDS_IN_DAY)
    }, [])

    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        setIsDragging(true)
        const time = getTimeFromEvent(e.clientX)
        setScrubberTime(time)
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)
    }, [getTimeFromEvent])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging) return
        const time = getTimeFromEvent(e.clientX)
        setScrubberTime(time)
    }, [isDragging, getTimeFromEvent])

    const handlePointerUp = useCallback(() => {
        if (!isDragging || scrubberTime === null) return
        setIsDragging(false)

        // Find segment at this time
        let foundSegment: Segment | null = null
        for (const seg of segments) {
            const segStart = parseTime(seg.time)
            const segEnd = segStart + seg.duration
            if (scrubberTime >= segStart && scrubberTime < segEnd) {
                foundSegment = seg
                break
            }
        }

        if (foundSegment) {
            const playlistUrl = getPlaylistUrl(camId, date, foundSegment.time)
            const jellyJumpUrl = getJellyJumpUrl(window.location.origin + playlistUrl)
            onPlayHls(jellyJumpUrl)
        }
    }, [isDragging, scrubberTime, segments, camId, date, onPlayHls])

    // Build coverage blocks
    const coverageBlocks = segments.map(seg => {
        const startSec = parseTime(seg.time)
        const leftPct = (startSec / SECONDS_IN_DAY) * 100
        const widthPct = (seg.duration / SECONDS_IN_DAY) * 100
        return { leftPct, widthPct }
    })

    const hasSegments = segments.length > 0

    return (
        <div className="time-scroller">
            {/* Compact header with time and live button */}
            <div className="scroller-header">
                {scrubberTime !== null ? (
                    <span className="scroller-time">{formatTimeShort(scrubberTime)}</span>
                ) : (
                    <span className="scroller-hint">Drag to seek</span>
                )}
                <button className="btn-live-pill" onClick={onPlayLive}>
                    🔴 Live
                </button>
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
                            width: `${Math.max(block.widthPct, 0.2)}%`,
                        }}
                    />
                ))}

                {/* Scrubber */}
                {scrubberTime !== null && (
                    <div
                        className="scrubber"
                        style={{ left: `${(scrubberTime / SECONDS_IN_DAY) * 100}%` }}
                    />
                )}

                {/* No recordings indicator */}
                {!loading && !hasSegments && (
                    <div className="no-recordings">No recordings</div>
                )}
            </div>

            {/* Simple hour markers */}
            <div className="hour-markers">
                <span>0</span>
                <span>6</span>
                <span>12</span>
                <span>18</span>
                <span>24</span>
            </div>
        </div>
    )
}

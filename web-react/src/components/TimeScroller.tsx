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

function formatTime(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

/**
 * TimeScroller - A draggable timeline for seeking through HLS recordings
 * 
 * Features:
 * - Displays 24-hour timeline with colored segments for recordings
 * - Draggable scrubber to seek to any time
 * - Generates HLS playlist URLs for time-range playback
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

    // Convert mouse/touch position to time
    const getTimeFromEvent = useCallback((clientX: number): number => {
        if (!trackRef.current) return 0
        const rect = trackRef.current.getBoundingClientRect()
        const x = Math.max(0, Math.min(clientX - rect.left, rect.width))
        const pct = x / rect.width
        return Math.floor(pct * SECONDS_IN_DAY)
    }, [])

    // Handle mouse/touch down
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        setIsDragging(true)
        const time = getTimeFromEvent(e.clientX)
        setScrubberTime(time)
            // Capture pointer for smooth dragging
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)
    }, [getTimeFromEvent])

    // Handle mouse/touch move
    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging) return
        const time = getTimeFromEvent(e.clientX)
        setScrubberTime(time)
    }, [isDragging, getTimeFromEvent])

    // Handle mouse/touch up - trigger playback
    const handlePointerUp = useCallback(() => {
        if (!isDragging || scrubberTime === null) return
        setIsDragging(false)

        // Find the segment that contains this time
        const targetTime = formatTime(scrubberTime)

        // Get the segment at or before the scrubber time
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
            // Generate playlist URL starting from this segment
            const playlistUrl = getPlaylistUrl(camId, date, foundSegment.time)
            const jellyJumpUrl = getJellyJumpUrl(window.location.origin + playlistUrl)
            onPlayHls(jellyJumpUrl)
        } else {
            // No recording at this time - could show a message or do nothing
            console.log('No recording at', targetTime)
        }
    }, [isDragging, scrubberTime, segments, camId, date, onPlayHls])

    // Build coverage map for visualization
    const coverageBlocks = segments.map(seg => {
        const startSec = parseTime(seg.time)
        const leftPct = (startSec / SECONDS_IN_DAY) * 100
        const widthPct = (seg.duration / SECONDS_IN_DAY) * 100
        return { leftPct, widthPct, time: seg.time }
    })

    // Check if current time is in a "live" segment (most recent segment, modified recently)
    const hasLiveSegment = segments.length > 0 && segments[segments.length - 1]

    return (
        <div className="time-scroller">
            <div className="scroller-header">
                <span className="scroller-label">Time Scroll</span>
                {scrubberTime !== null && (
                    <span className="scroller-time">{formatTime(scrubberTime)}</span>
                )}
                <button
                    className="btn btn-live-small"
                    onClick={onPlayLive}
                    title="Switch to live view"
                >
                    🔴 Live
                </button>
            </div>

            <div
                ref={trackRef}
                className={`scroller-track ${isDragging ? 'dragging' : ''} ${loading ? 'loading' : ''}`}
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
                            width: `${Math.max(block.widthPct, 0.15)}%`,
                        }}
                        title={block.time}
                    />
                ))}

                {/* Live indicator at current time */}
                {hasLiveSegment && (
                    <div
                        className="live-indicator"
                        style={{
                            left: `${(parseTime(segments[segments.length - 1].time) / SECONDS_IN_DAY) * 100}%`
                        }}
                    />
                )}

                {/* Scrubber */}
                {scrubberTime !== null && (
                    <div
                        className="scrubber"
                        style={{
                            left: `${(scrubberTime / SECONDS_IN_DAY) * 100}%`
                        }}
                    />
                )}
            </div>

            <div className="scroller-labels">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>24:00</span>
            </div>
        </div>
    )
}

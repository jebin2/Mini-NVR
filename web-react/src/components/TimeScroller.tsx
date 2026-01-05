import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Segment, fetchSegments, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl } from '../services/go2rtc'
import './TimeScroller.css'

interface TimeScrollerProps {
    camId: string
    date: string
    availableDates: string[]
    onDateChange: (date: string) => void
    isLive: boolean
    videoTime?: number | null
    playlistStart?: number | null
    onPlayHls: (url: string) => void
    onPlayLive: () => void
    playMode: 'live' | 'buffer'
    onModeChange: (mode: 'live' | 'buffer') => void
    // New Props for Gap Logic
    onGapChange: (isGap: boolean, nextSegTime: number | null) => void
    externalForceTime?: number | null
}

const ZOOM_MINUTES = 30
const SECONDS_IN_DAY = 86400

function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

function formatTimeShort(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function getShiftedDate(currentDateStr: string, shiftDays: number): string {
    const d = new Date(currentDateStr)
    d.setDate(d.getDate() + shiftDays)
    return d.toISOString().split('T')[0]
}

export default function TimeScroller({
    camId, date, availableDates, onDateChange,
    isLive, videoTime, playlistStart,
    onPlayHls, onPlayLive,
    playMode, onModeChange,
    onGapChange, externalForceTime
}: TimeScrollerProps) {
    const [segments, setSegments] = useState<Segment[]>([])
    const [loading, setLoading] = useState(true)

    // The time at the CENTER of the scrubber
    const [currentTime, setCurrentTime] = useState(0)
    const [isDragging, setIsDragging] = useState(false)

    // Track when user last released drag to debounce video updates
    const lastInteractionTimeRef = useRef(0)

    // For smooth scrolling with requestAnimationFrame
    const rafRef = useRef<number | null>(null)
    const pendingDeltaRef = useRef(0)

    const trackRef = useRef<HTMLDivElement>(null)

    // Use ref for isDragging to prevent callback recreation during parent re-renders
    const isDraggingRef = useRef(false)

    // Track previous gap state to avoid redundant calls
    const prevGapStateRef = useRef<{ isGap: boolean; nextTime: number | null }>({ isGap: false, nextTime: null })

    // Helper: Get current time of day in seconds
    const getCurrentTimeSeconds = () => {
        const now = new Date()
        return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    }

    // Load segments
    useEffect(() => {
        let isMounted = true
        let intervalId: number | null = null

        async function load() {
            setLoading(prev => prev || true)
            try {
                const data = await fetchSegments(camId, date)
                if (!isMounted) return
                setSegments(data.segments)

                // Initial positioning if not live and valid data exists
                if (!isLive && data.segments.length > 0 && loading) {
                    const lastSeg = data.segments[data.segments.length - 1]
                    const lastTime = parseTime(lastSeg.time) + lastSeg.duration
                    setCurrentTime(lastTime - 10) // 10s before end
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                if (isMounted) setSegments([])
            }
            if (isMounted) setLoading(false)
        }

        load()

        const today = new Date().toISOString().split('T')[0]
        if (date === today) {
            intervalId = window.setInterval(load, 15000)
        }

        return () => {
            isMounted = false
            if (intervalId) clearInterval(intervalId)
        }
    }, [camId, date])

    // External Force Time (from "Go Next" button)
    useEffect(() => {
        if (externalForceTime != null) {
            setCurrentTime(externalForceTime)
            // Trigger play immediately
            triggerPlayAt(externalForceTime, segments)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [externalForceTime])

    // Helper to find segment and play
    const triggerPlayAt = (time: number, segs: Segment[]) => {
        let found: Segment | null = null
        for (const seg of segs) {
            const start = parseTime(seg.time)
            const end = start + seg.duration
            if (time >= start && time < end) {
                found = seg
                break
            }
        }
        if (found) {
            const url = getPlaylistUrl(camId, date, found.time)
            onPlayHls(getJellyJumpUrl(window.location.origin + url))
        }
        if (playMode === 'live') {
            onModeChange('buffer')
        }
    }

    // Gap Detection & Simulated Playback Loop
    // IMPORTANT: Only run when NOT dragging to avoid jerkiness
    useEffect(() => {
        // Skip gap detection entirely while dragging
        if (isDragging) return
        if (isLive || loading) return

        // 1. check if gap
        const hasVideo = segments.some(seg => {
            const s = parseTime(seg.time)
            const e = s + seg.duration
            return currentTime >= s && currentTime < e
        })

        // 2. Find next segment time
        let nextTime: number | null = null
        if (!hasVideo) {
            const nextSeg = segments.find(s => parseTime(s.time) > currentTime)
            if (nextSeg) nextTime = parseTime(nextSeg.time)
        }

        // Only notify parent if gap state CHANGED (avoid redundant re-renders)
        const isGap = !hasVideo
        if (prevGapStateRef.current.isGap !== isGap || prevGapStateRef.current.nextTime !== nextTime) {
            prevGapStateRef.current = { isGap, nextTime }
            onGapChange(isGap, nextTime)
        }

        // 3. If gap, simulate playback (tick every second)
        let timer: number | null = null

        if (!hasVideo && segments.length > 0) {
            timer = window.setInterval(() => {
                setCurrentTime(t => {
                    const next = t + 1
                    return next > SECONDS_IN_DAY ? SECONDS_IN_DAY : next
                })
            }, 1000)
        }

        return () => {
            if (timer) clearInterval(timer)
        }
    }, [isLive, isDragging, currentTime, segments, loading, onGapChange])

    // Local helper 
    function hasVideoAtCurrentTimeLocal(time: number, segs: Segment[]) {
        return segs.some(seg => {
            const s = parseTime(seg.time)
            const e = s + seg.duration
            return time >= s && time < e
        })
    }


    // Sync with video playback (only if NOT dragging and grace period passed)
    useEffect(() => {
        if (isDragging || isLive || videoTime == null || playlistStart == null) return

        // Grace period check (3 seconds to allow new video to load)
        if (Date.now() - lastInteractionTimeRef.current < 3000) return

        // Calculate actual time from videoTime
        if (segments.length > 0) {
            const relevantSegments = segments.filter(s => parseTime(s.time) >= playlistStart)
            if (relevantSegments.length === 0) return

            let cumulativeVideoTime = 0
            let actualTime = playlistStart

            for (const seg of relevantSegments) {
                const segStart = parseTime(seg.time)
                const segDuration = seg.duration

                if (videoTime < cumulativeVideoTime + segDuration) {
                    actualTime = segStart + (videoTime - cumulativeVideoTime)
                    break
                }
                cumulativeVideoTime += segDuration
                actualTime = segStart + segDuration
            }
            setCurrentTime(actualTime)
        }
    }, [isLive, videoTime, playlistStart, segments, isDragging])

    // Live mode clock
    useEffect(() => {
        if (!isLive || isDragging) return

        const updateClock = () => {
            setCurrentTime(getCurrentTimeSeconds())
        }
        updateClock()
        const interval = setInterval(updateClock, 1000)
        return () => clearInterval(interval)
    }, [isLive, isDragging])


    // Pointer Events for Dragging
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        isDraggingRef.current = true
        setIsDragging(true);
        (e.target as HTMLElement).setPointerCapture(e.pointerId)
    }, [])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        // Use ref to check drag state (avoids callback recreation)
        if (!isDraggingRef.current || !trackRef.current) return

        const rect = trackRef.current.getBoundingClientRect()
        const secondsPerPixel = (ZOOM_MINUTES * 60) / rect.width

        // Accumulate delta for batching with requestAnimationFrame
        pendingDeltaRef.current += -e.movementX * secondsPerPixel

        // Only schedule RAF if not already pending
        if (rafRef.current === null) {
            rafRef.current = requestAnimationFrame(() => {
                const delta = pendingDeltaRef.current
                pendingDeltaRef.current = 0
                rafRef.current = null

                setCurrentTime(t => {
                    let next = t + delta

                    // Seamless Day Switching
                    if (next < 0) {
                        onDateChange(getShiftedDate(date, -1))
                        next = SECONDS_IN_DAY + next
                    } else if (next > SECONDS_IN_DAY) {
                        onDateChange(getShiftedDate(date, 1))
                        next = next - SECONDS_IN_DAY
                    }

                    return next
                })
            })
        }
    }, [date, onDateChange])  // Removed isDragging from deps - we use ref now

    // On Drag End Logic
    const onDragEnd = useCallback(() => {
        // Use ref to check (more reliable than state during rapid interactions)
        if (!isDraggingRef.current) return

        // Cancel any pending RAF
        if (rafRef.current !== null) {
            cancelAnimationFrame(rafRef.current)
            rafRef.current = null
        }

        // Calculate final landing time synchronously (avoid stale closure)
        let finalTime = currentTime
        if (pendingDeltaRef.current !== 0) {
            finalTime = currentTime + pendingDeltaRef.current
            pendingDeltaRef.current = 0
            if (finalTime < 0) finalTime = SECONDS_IN_DAY + finalTime
            else if (finalTime > SECONDS_IN_DAY) finalTime = finalTime - SECONDS_IN_DAY
        }

        // Update both ref and state
        isDraggingRef.current = false
        setCurrentTime(finalTime)
        setIsDragging(false)
        lastInteractionTimeRef.current = Date.now()

        // Trigger Play immediately at the FINAL landing spot (not from closure)
        triggerPlayAt(finalTime, segments)

        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isDragging, currentTime, segments])

    const handlePointerUp = onDragEnd

    // RENDER HELPERS
    // Memoize tick calculations to reduce re-renders during drag
    const ticks = useMemo(() => {
        const viewportSeconds = ZOOM_MINUTES * 60
        const halfViewport = viewportSeconds / 2
        const viewStart = currentTime - halfViewport
        const viewEnd = currentTime + halfViewport

        const getLeftPct = (time: number) => {
            return ((time - viewStart) / viewportSeconds) * 100
        }

        const result: { pct: number; label: string | null; type: 'major' | 'minor' }[] = []
        const majorInterval = 5 * 60
        const minorInterval = 1 * 60
        const startTick = Math.floor(viewStart / minorInterval) * minorInterval

        for (let t = startTick; t <= viewEnd; t += minorInterval) {
            let normalizedTime = t
            if (t < 0) normalizedTime = SECONDS_IN_DAY + t
            else if (t >= SECONDS_IN_DAY) normalizedTime = t - SECONDS_IN_DAY

            const isMajor = (t % majorInterval === 0)
            let label = null
            if (isMajor) {
                label = formatTimeShort(normalizedTime).slice(0, 5)
            }

            result.push({
                pct: getLeftPct(t),
                label,
                type: isMajor ? 'major' : 'minor'
            })
        }
        return result
    }, [currentTime])

    const hasVideoAtCurrentTime = hasVideoAtCurrentTimeLocal(currentTime, segments)

    return (
        <div className="time-scroller">
            {/* Header */}
            <div className="scroller-header">
                <div className="date-select-wrapper">
                    <select className="date-select" value={date} onChange={(e) => onDateChange(e.target.value)}>
                        {availableDates.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                </div>

                <div className="time-display-center">
                    <span className="current-time-large">{formatTimeShort(currentTime)}</span>
                </div>

                <div className="mode-toggle">
                    <button className={`mode-btn ${playMode === 'live' ? 'active' : ''}`} onClick={() => {
                        onPlayLive()
                        onModeChange('live')
                    }}>Live</button>
                    <button className={`mode-btn ${playMode === 'buffer' ? 'active' : ''}`} onClick={() => onModeChange('buffer')}>Rec</button>
                </div>
            </div>

            {/* Scrubber Track */}
            <div
                className="scroller-container ruler-style"
                ref={trackRef}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                onPointerLeave={handlePointerUp}
            >
                {/* Ruler Ticks */}
                {ticks.map((tick, i) => (
                    <div
                        key={i}
                        className={`ruler-tick ${tick.type}`}
                        style={{ left: `${tick.pct}%` }}
                    >
                        {tick.label && <span className="tick-label">{tick.label}</span>}
                    </div>
                ))}

                {/* Center Line (Fixed) */}
                <div className="center-line" />

                {/* No Video Overlay - Visual Strip */}
                {!hasVideoAtCurrentTime && !loading && segments.length > 0 && (
                    <div className="no-video-strip" />
                )}
            </div>
        </div>
    )
}

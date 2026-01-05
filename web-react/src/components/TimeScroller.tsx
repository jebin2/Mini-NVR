import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Segment, fetchSegments, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl } from '../services/go2rtc'
import { getLocalDateString } from '../utils/dateUtils'
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
    onGapChange: (isGap: boolean, nextSegTime: number | null, isFuture: boolean) => void
    externalForceTime?: number | null
}

const ZOOM_MINUTES = 30
const SECONDS_IN_DAY = 86400
const GAP_DEBOUNCE_MS = 500        // Debounce for gap detection after interaction

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

// Helper: check if time falls within any segment
function hasVideoAt(time: number, segs: Segment[]): boolean {
    return segs.some(seg => {
        const s = parseTime(seg.time)
        return time >= s && time < s + seg.duration
    })
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
    const [currentTime, setCurrentTime] = useState(0)
    const [isDragging, setIsDragging] = useState(false)

    // === REFS ===
    const refs = useRef({
        isDragging: false,
        currentTime: 0,
        lastInteraction: 0,
        pendingDelta: 0,
        raf: null as number | null,
        prevGap: { isGap: false, nextTime: null as number | null, isFuture: false },
        isSeeking: false,
        seekTarget: 0,
        seekTimeout: null as number | null
    })

    // Keep currentTime ref in sync
    refs.current.currentTime = currentTime

    const trackRef = useRef<HTMLDivElement>(null)

    // === HELPERS ===
    const getCurrentTimeSeconds = () => {
        const now = new Date()
        return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
    }

    const isWithinGapDebounce = () => Date.now() - refs.current.lastInteraction < GAP_DEBOUNCE_MS

    const triggerPlayAt = useCallback((time: number, segs: Segment[]) => {
        const found = segs.find(seg => {
            const start = parseTime(seg.time)
            return time >= start && time < start + seg.duration
        })
        if (found) {
            const url = getPlaylistUrl(camId, date, found.time)
            onPlayHls(getJellyJumpUrl(window.location.origin + url))
        }
        if (playMode === 'live') {
            onModeChange('buffer')
        }
    }, [camId, date, onPlayHls, playMode, onModeChange])

    // === EFFECTS ===

    // 1. Load segments
    useEffect(() => {
        let isMounted = true
        let intervalId: number | null = null

        async function load() {
            setLoading(true)
            try {
                const data = await fetchSegments(camId, date)
                if (!isMounted) return
                setSegments(data.segments)

                if (!isLive && data.segments.length > 0) {
                    const lastSeg = data.segments[data.segments.length - 1]
                    const lastTime = parseTime(lastSeg.time) + lastSeg.duration
                    setCurrentTime(lastTime - 10)
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                if (isMounted) setSegments([])
            }
            if (isMounted) setLoading(false)
        }

        load()

        const today = getLocalDateString(new Date())

        if (date === today) {
            intervalId = window.setInterval(load, 15000)
        }

        return () => {
            isMounted = false
            if (intervalId) clearInterval(intervalId)
        }
    }, [camId, date, isLive])

    // 2. External force time (from "Go Next" button)
    useEffect(() => {
        if (externalForceTime != null) {
            setCurrentTime(externalForceTime)
            triggerPlayAt(externalForceTime, segments)
        }
    }, [externalForceTime, segments, triggerPlayAt])

    // 3. Gap detection (with debounce)
    useEffect(() => {
        if (isDragging || isLive || loading) return

        // Wait for debounce period after any interaction
        if (isWithinGapDebounce()) {
            const remaining = GAP_DEBOUNCE_MS - (Date.now() - refs.current.lastInteraction)
            const timeoutId = setTimeout(() => setCurrentTime(t => t), remaining + 10)
            return () => clearTimeout(timeoutId)
        }

        const hasVideo = hasVideoAt(currentTime, segments)
        let nextTime: number | null = null
        let isFuture = false

        if (!hasVideo) {
            const nextSeg = segments.find(s => parseTime(s.time) > currentTime)
            if (nextSeg) {
                nextTime = parseTime(nextSeg.time)
            } else if (segments.length > 0) {
                const lastSeg = segments[segments.length - 1]
                if (currentTime >= parseTime(lastSeg.time) + lastSeg.duration) {
                    isFuture = true
                }
            }
        }

        // Only notify if changed
        // IMPORTANT: Don't report gap if segments haven't loaded - prevents iframe unmount during load
        const prev = refs.current.prevGap
        const isGap = !hasVideo && segments.length > 0  // Only gap if we HAVE segments but none match
        if (prev.isGap !== isGap || prev.nextTime !== nextTime || prev.isFuture !== isFuture) {
            refs.current.prevGap = { isGap, nextTime, isFuture }
            onGapChange(isGap, nextTime, isFuture)
        }

        // Simulate playback in gaps (tick forward)
        // No timer needed - clean/simple
    }, [isLive, isDragging, currentTime, segments, loading, onGapChange])

    // 4. Video Sync (Unidirectional: Video -> Scrubber)
    // Only update scrubber if user is NOT dragging
    useEffect(() => {
        if (isDragging || isLive || videoTime == null || playlistStart == null) return

        // 1. GAP HANDLING: If scrubber is in a gap, DISABLE sync.
        // We trust the scrubber position absolutely in gaps.
        if (!hasVideoAt(refs.current.currentTime, segments)) return

        // Calculate server time from video time
        // Video time is relative to playlist start
        const relevantSegments = segments.filter(s => parseTime(s.time) >= playlistStart)
        if (relevantSegments.length === 0) return

        let cumulative = 0
        let actualTime = playlistStart

        for (const seg of relevantSegments) {
            const segStart = parseTime(seg.time)
            if (videoTime < cumulative + seg.duration) {
                actualTime = segStart + (videoTime - cumulative)
                break
            }
            cumulative += seg.duration
            actualTime = segStart + seg.duration
        }

        // 2. SEEK LOCKING: Prevent "jerky" jumps after scrubbing
        // If we are waiting for a seek to complete, ignore video updates 
        // until the video is close to our target time.
        if (refs.current.isSeeking) {
            const diff = Math.abs(actualTime - refs.current.seekTarget)
            if (diff < 2) {
                // Video has caught up! Unlock.
                refs.current.isSeeking = false
                if (refs.current.seekTimeout) clearTimeout(refs.current.seekTimeout)
            } else {
                // Video is still stale/seeking. Ignore it.
                return
            }
        }

        // Normal Sync (Unidirectional)
        if (Math.abs(actualTime - refs.current.currentTime) > 1) {
            setCurrentTime(actualTime)
        }
    }, [isLive, videoTime, playlistStart, segments, isDragging])

    // 5. Live mode clock
    useEffect(() => {
        if (!isLive || isDragging) return

        const update = () => setCurrentTime(getCurrentTimeSeconds())
        update()
        const interval = setInterval(update, 1000)
        return () => clearInterval(interval)
    }, [isLive, isDragging])

    // === POINTER HANDLERS ===
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        refs.current.isDragging = true
        setIsDragging(true)
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)
    }, [])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!refs.current.isDragging || !trackRef.current) return

        const rect = trackRef.current.getBoundingClientRect()
        const secondsPerPixel = (ZOOM_MINUTES * 60) / rect.width
        refs.current.pendingDelta += -e.movementX * secondsPerPixel

        if (refs.current.raf === null) {
            refs.current.raf = requestAnimationFrame(() => {
                const delta = refs.current.pendingDelta
                refs.current.pendingDelta = 0
                refs.current.raf = null

                setCurrentTime(t => {
                    let next = t + delta
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
    }, [date, onDateChange])

    const handlePointerUp = useCallback(() => {
        if (!refs.current.isDragging) return

        // Cancel pending animation
        if (refs.current.raf !== null) {
            cancelAnimationFrame(refs.current.raf)
            refs.current.raf = null
        }

        // Calculate final time from REF (not stale closure)
        let finalTime = refs.current.currentTime + refs.current.pendingDelta
        refs.current.pendingDelta = 0

        if (finalTime < 0) finalTime = SECONDS_IN_DAY + finalTime
        else if (finalTime > SECONDS_IN_DAY) finalTime = finalTime - SECONDS_IN_DAY

        // Update state
        refs.current.isDragging = false
        refs.current.lastInteraction = Date.now()
        setCurrentTime(finalTime)
        setIsDragging(false)

        // ENABLE SEEK LOCK
        // We expect the video to take a moment to seek.
        // Lock the scrubber until video reports a time close to finalTime.
        refs.current.isSeeking = true
        refs.current.seekTarget = finalTime
        // Safety timeout: If video never catches up (e.g. error), unlock after 5s
        if (refs.current.seekTimeout) clearTimeout(refs.current.seekTimeout)
        refs.current.seekTimeout = window.setTimeout(() => {
            refs.current.isSeeking = false
        }, 5000)

        // Play at final position
        triggerPlayAt(finalTime, segments)
    }, [segments, triggerPlayAt])

    // === RENDER ===
    const ticks = useMemo(() => {
        const viewportSeconds = ZOOM_MINUTES * 60
        const halfViewport = viewportSeconds / 2
        const viewStart = currentTime - halfViewport
        const viewEnd = currentTime + halfViewport

        const result: { pct: number; label: string | null; type: 'major' | 'minor' }[] = []
        const majorInterval = 5 * 60
        const minorInterval = 1 * 60
        const startTick = Math.floor(viewStart / minorInterval) * minorInterval

        for (let t = startTick; t <= viewEnd; t += minorInterval) {
            let normalizedTime = t
            if (t < 0) normalizedTime = SECONDS_IN_DAY + t
            else if (t >= SECONDS_IN_DAY) normalizedTime = t - SECONDS_IN_DAY

            const isMajor = t % majorInterval === 0
            result.push({
                pct: ((t - viewStart) / viewportSeconds) * 100,
                label: isMajor ? formatTimeShort(normalizedTime).slice(0, 5) : null,
                type: isMajor ? 'major' : 'minor'
            })
        }
        return result
    }, [currentTime])

    const hasVideoAtCurrentTime = hasVideoAt(currentTime, segments)

    return (
        <div className="time-scroller">
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
                    <button className={`mode-btn ${playMode === 'buffer' ? 'active' : ''}`} onClick={() => {
                        onModeChange('buffer')
                    }}>Rec</button>
                </div>
            </div>

            <div
                className="scroller-container ruler-style"
                ref={trackRef}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                onPointerLeave={handlePointerUp}
            >
                {ticks.map((tick, i) => (
                    <div
                        key={i}
                        className={`ruler-tick ${tick.type}`}
                        style={{ left: `${tick.pct}%` }}
                    >
                        {tick.label && <span className="tick-label">{tick.label}</span>}
                    </div>
                ))}

                <div className="center-line" />

                {!hasVideoAtCurrentTime && !loading && segments.length > 0 && (
                    <div className="no-video-strip" />
                )}
            </div>
        </div>
    )
}

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { getLocalDateString } from '../utils/dateUtils'
import './TimeScroller.css'

interface TimeScrollerProps {
    camId: string
    date: string
    availableDates: string[]
    onDateChange: (date: string) => void
    onScrollStart: () => void
    onScrollEnd: (time: number) => void
    onGoLive: () => void  // Callback when user clicks live indicator
    externalForceTime?: number | null
    segmentStartTime?: number | null
    playerTime?: number | null
}

// === CONSTANTS ===
const ZOOM_MINUTES = 30
const SECONDS_IN_DAY = 86400
const LIVE_THRESHOLD = 45  // Consider "live" if within 45s of current time

// === PURE HELPERS ===

function formatTimeShort(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function shiftDate(dateStr: string, days: number): string {
    const d = new Date(dateStr)
    d.setDate(d.getDate() + days)
    return d.toISOString().split('T')[0]
}

function wrapTime(time: number, currentDate: string): { time: number; date: string; dateChanged: boolean } {
    if (time < 0) {
        return { time: SECONDS_IN_DAY + time, date: shiftDate(currentDate, -1), dateChanged: true }
    }
    if (time >= SECONDS_IN_DAY) {
        return { time: time - SECONDS_IN_DAY, date: shiftDate(currentDate, 1), dateChanged: true }
    }
    return { time, date: currentDate, dateChanged: false }
}

function getCurrentTimeSeconds(): number {
    const now = new Date()
    return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
}

// === COMPONENT ===

export default function TimeScroller({
    camId: _camId, date, availableDates, onDateChange,
    onScrollStart, onScrollEnd, onGoLive, externalForceTime,
    segmentStartTime, playerTime
}: TimeScrollerProps) {

    // === STATE ===
    const [currentTime, setCurrentTime] = useState(0)
    const [isDragging, setIsDragging] = useState(false)
    const [currentDate, setCurrentDate] = useState(date)
    const [userSelectedTime, setUserSelectedTime] = useState<number | null>(null)

    // === REFS ===
    const trackRef = useRef<HTMLDivElement>(null)
    const debounceRef = useRef<number | null>(null)

    // === CLEANUP ===
    useEffect(() => {
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current)
        }
    }, [])

    // Sync date prop -> internal state
    useEffect(() => {
        setCurrentDate(date)
    }, [date])

    // === EXTERNAL FORCE TIME ===
    useEffect(() => {
        if (externalForceTime != null) {
            setCurrentTime(externalForceTime)
            setUserSelectedTime(externalForceTime)
            onScrollEnd(externalForceTime)
        }
    }, [externalForceTime])

    // === VIDEO SYNC ===
    useEffect(() => {
        if (isDragging) return
        if (segmentStartTime == null || playerTime == null) return

        const actualVideoTime = segmentStartTime + playerTime

        if (userSelectedTime != null) {
            if (actualVideoTime < userSelectedTime) {
                return
            }
            setUserSelectedTime(null)
        }

        if (Math.abs(actualVideoTime - currentTime) > 1) {
            setCurrentTime(actualVideoTime)
        }
    }, [segmentStartTime, playerTime, isDragging, userSelectedTime, currentTime])

    // === IS NEAR LIVE? ===
    const isNearLive = useMemo(() => {
        const today = getLocalDateString(new Date())
        if (currentDate !== today) return false

        const now = getCurrentTimeSeconds()
        const diff = now - currentTime
        return diff >= 0 && diff <= LIVE_THRESHOLD
    }, [currentDate, currentTime])

    // === POINTER HANDLERS ===
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        setIsDragging(true)
        onScrollStart()
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)

        if (debounceRef.current) {
            clearTimeout(debounceRef.current)
            debounceRef.current = null
        }
    }, [onScrollStart])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging || !trackRef.current) return

        const rect = trackRef.current.getBoundingClientRect()
        const secondsPerPixel = (ZOOM_MINUTES * 60) / rect.width
        const delta = -e.movementX * secondsPerPixel

        setCurrentTime(prevTime => {
            const newTime = prevTime + delta
            const wrapped = wrapTime(newTime, currentDate)

            if (wrapped.dateChanged) {
                setCurrentDate(wrapped.date)
                onDateChange(wrapped.date)
            }

            return wrapped.time
        })
    }, [isDragging, currentDate, onDateChange])

    const handlePointerUp = useCallback(() => {
        if (!isDragging) return

        setIsDragging(false)
        setUserSelectedTime(currentTime)

        debounceRef.current = window.setTimeout(() => {
            onScrollEnd(currentTime)
            debounceRef.current = null
        }, 400)
    }, [isDragging, currentTime, onScrollEnd])

    // Click to jump to a specific time
    const handleClick = useCallback((e: React.MouseEvent) => {
        if (!trackRef.current) return

        // Only handle direct clicks, not drag releases
        // If we were dragging, skip this
        if (isDragging) return

        const rect = trackRef.current.getBoundingClientRect()
        const clickX = e.clientX - rect.left
        const clickPct = clickX / rect.width

        // Calculate time at click position
        const viewportSeconds = ZOOM_MINUTES * 60
        const halfViewport = viewportSeconds / 2
        const viewStart = currentTime - halfViewport
        const clickedTime = viewStart + (clickPct * viewportSeconds)

        // Wrap and apply
        const wrapped = wrapTime(clickedTime, currentDate)
        if (wrapped.dateChanged) {
            setCurrentDate(wrapped.date)
            onDateChange(wrapped.date)
        }

        setCurrentTime(wrapped.time)
        setUserSelectedTime(wrapped.time)

        // Trigger video load
        onScrollStart()
        debounceRef.current = window.setTimeout(() => {
            onScrollEnd(wrapped.time)
            debounceRef.current = null
        }, 400)
    }, [currentTime, currentDate, isDragging, onDateChange, onScrollStart, onScrollEnd])

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

    return (
        <div className="time-scroller">
            <div className="scroller-header">
                <div className="date-select-wrapper">
                    <select
                        className="date-select"
                        value={currentDate}
                        onChange={(e) => {
                            setCurrentDate(e.target.value)
                            onDateChange(e.target.value)
                        }}
                    >
                        {availableDates.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                </div>

                <div className="time-display-center">
                    <span className="current-time-large">{formatTimeShort(currentTime)}</span>

                    {/* Live Indicator */}
                    <button
                        className={`live-indicator ${isNearLive ? 'is-live' : 'is-faded'}`}
                        onClick={onGoLive}
                        title={isNearLive ? 'Currently live' : 'Go to live'}
                    >
                        <span className="live-dot" />
                        <span className="live-text">LIVE</span>
                    </button>
                </div>
            </div>

            <div
                className={`scroller-container ruler-style ${isDragging ? 'is-dragging' : ''}`}
                ref={trackRef}
                onClick={handleClick}
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
            </div>
        </div>
    )
}

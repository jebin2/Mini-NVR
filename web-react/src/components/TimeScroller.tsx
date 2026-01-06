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
    onGoLive: () => void
    externalForceTime?: number | null
    segmentStartTime?: number | null
    playerTime?: number | null
}

// === CONSTANTS ===
const ZOOM_MINUTES = 30
const SECONDS_IN_DAY = 86400
const LIVE_THRESHOLD = 45
const FRICTION = 0.95  // Momentum friction (0.95 = smooth deceleration)
const MIN_VELOCITY = 0.5  // Stop animation when velocity below this

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
    const velocityRef = useRef(0)  // Track velocity for momentum
    const lastMoveTimeRef = useRef(0)  // Time of last move event
    const animationRef = useRef<number | null>(null)  // requestAnimationFrame ID
    const currentTimeRef = useRef(0)  // Non-reactive time for animation
    const currentDateRef = useRef(date)  // Non-reactive date for animation
    const justDraggedRef = useRef(false)  // Prevent click after drag

    // Keep refs in sync with state
    useEffect(() => {
        currentTimeRef.current = currentTime
    }, [currentTime])

    useEffect(() => {
        currentDateRef.current = currentDate
    }, [currentDate])

    // === CLEANUP ===
    useEffect(() => {
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current)
            if (animationRef.current) cancelAnimationFrame(animationRef.current)
        }
    }, [])

    // Sync date prop -> internal state
    useEffect(() => {
        setCurrentDate(date)
        currentDateRef.current = date
    }, [date])

    // === EXTERNAL FORCE TIME ===
    useEffect(() => {
        if (externalForceTime != null) {
            // Stop any ongoing momentum animation
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current)
                animationRef.current = null
            }
            velocityRef.current = 0

            setCurrentTime(externalForceTime)
            setUserSelectedTime(externalForceTime)
            onScrollEnd(externalForceTime)
        }
    }, [externalForceTime])

    // === VIDEO SYNC ===
    useEffect(() => {
        if (isDragging) return
        if (segmentStartTime == null || playerTime == null) return
        if (animationRef.current) return  // Don't sync during momentum animation

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

    // === MOMENTUM ANIMATION ===
    const animateMomentum = useCallback(() => {
        const velocity = velocityRef.current

        // Stop if velocity is too low
        if (Math.abs(velocity) < MIN_VELOCITY) {
            velocityRef.current = 0
            animationRef.current = null

            // Trigger video load after momentum stops
            const finalTime = currentTimeRef.current
            setUserSelectedTime(finalTime)
            debounceRef.current = window.setTimeout(() => {
                onScrollEnd(finalTime)
                debounceRef.current = null
            }, 400)
            return
        }

        // Apply friction
        velocityRef.current *= FRICTION

        // Update time
        const newTime = currentTimeRef.current + velocityRef.current
        const wrapped = wrapTime(newTime, currentDateRef.current)

        if (wrapped.dateChanged) {
            currentDateRef.current = wrapped.date
            setCurrentDate(wrapped.date)
            onDateChange(wrapped.date)
        }

        currentTimeRef.current = wrapped.time
        setCurrentTime(wrapped.time)

        // Continue animation
        animationRef.current = requestAnimationFrame(animateMomentum)
    }, [onDateChange, onScrollEnd])

    // === POINTER HANDLERS ===
    const handlePointerDown = useCallback((e: React.PointerEvent) => {
        // Stop any ongoing momentum animation
        if (animationRef.current) {
            cancelAnimationFrame(animationRef.current)
            animationRef.current = null
        }
        velocityRef.current = 0

        setIsDragging(true)
        onScrollStart()
            ; (e.target as HTMLElement).setPointerCapture(e.pointerId)

        if (debounceRef.current) {
            clearTimeout(debounceRef.current)
            debounceRef.current = null
        }

        lastMoveTimeRef.current = Date.now()
    }, [onScrollStart])

    const handlePointerMove = useCallback((e: React.PointerEvent) => {
        if (!isDragging || !trackRef.current) return

        const rect = trackRef.current.getBoundingClientRect()
        const secondsPerPixel = (ZOOM_MINUTES * 60) / rect.width
        const delta = -e.movementX * secondsPerPixel

        // Track velocity for momentum
        const now = Date.now()
        const dt = now - lastMoveTimeRef.current
        if (dt > 0) {
            // Weighted average for smoother velocity
            velocityRef.current = velocityRef.current * 0.5 + (delta / dt * 16) * 0.5
        }
        lastMoveTimeRef.current = now

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

        // Check if user was stopped before releasing
        // If no movement for 100ms+, don't apply momentum
        const timeSinceLastMove = Date.now() - lastMoveTimeRef.current
        if (timeSinceLastMove > 100) {
            velocityRef.current = 0
        }

        // Start momentum animation if velocity is significant
        if (Math.abs(velocityRef.current) > MIN_VELOCITY) {
            animationRef.current = requestAnimationFrame(animateMomentum)
        } else {
            // No momentum, trigger video load immediately
            setUserSelectedTime(currentTime)
            debounceRef.current = window.setTimeout(() => {
                onScrollEnd(currentTime)
                debounceRef.current = null
            }, 400)
        }

        // Mark that we just dragged - prevents click from firing
        justDraggedRef.current = true
        setTimeout(() => { justDraggedRef.current = false }, 50)
    }, [isDragging, currentTime, onScrollEnd, animateMomentum])

    // Click to jump to a specific time
    const handleClick = useCallback((e: React.MouseEvent) => {
        if (!trackRef.current) return
        if (isDragging) return

        // Skip click if we just finished dragging
        if (justDraggedRef.current) return

        // Don't handle click if we just finished momentum scrolling
        if (animationRef.current) return

        const rect = trackRef.current.getBoundingClientRect()
        const clickX = e.clientX - rect.left
        const clickPct = clickX / rect.width

        const viewportSeconds = ZOOM_MINUTES * 60
        const halfViewport = viewportSeconds / 2
        const viewStart = currentTime - halfViewport
        const clickedTime = viewStart + (clickPct * viewportSeconds)

        const wrapped = wrapTime(clickedTime, currentDate)
        if (wrapped.dateChanged) {
            setCurrentDate(wrapped.date)
            onDateChange(wrapped.date)
        }

        setCurrentTime(wrapped.time)
        setUserSelectedTime(wrapped.time)

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
                </div>

                {/* Live Indicator - Right column */}
                <div className="live-indicator-wrapper">
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

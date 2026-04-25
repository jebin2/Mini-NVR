import { useState, useEffect, useCallback, useRef } from 'react'
import { Channel, Segment, fetchDates, fetchSegments, fetchConfig, getHfPlaylistUrl, getPlaylistUrl } from '../services/api'
import { getJellyJumpUrl, getJellyJumpHfUrlWithSeek } from '../services/go2rtc'
import { fetchHfSegments, fetchLiveSegments, wallClockToOffset, offsetToWallClock, HfSegment } from '../services/hfPlaylist'
import { getLocalDateString } from '../utils/dateUtils'
import VideoPlayer from './VideoPlayer'
import InfoOverlay from './InfoOverlay'
import TimeScroller from './TimeScroller'
import './ExpandedView.css'

interface ExpandedViewProps {
    camId: string
    channels: Record<string, Channel>
}

function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

function findSegmentAt(time: number, segments: Segment[]): Segment | null {
    return segments.find(seg => {
        const start = parseTime(seg.time)
        return time >= start && time < start + seg.duration
    }) || null
}


function getCurrentSeconds(): number {
    const now = new Date()
    return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds()
}

function secondsToHMS(s: number): string {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = Math.floor(s % 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
}

// State machine — one source of truth for what's shown in the video area
type VideoAreaState =
    | { type: 'loading' }
    | { type: 'live'; url: string }   // ffmpeg _live.m3u8 (MPEG-TS, same format as VOD)
    | { type: 'vod'; url: string }    // HF HLS VOD (with start_time baked into URL)
    | { type: 'no-video'; nextTime: number | null }

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [forceTime, setForceTime] = useState<number | null>(null)

    // HF segments (wall-clock ↔ offset map) — parsed from HF playlist.m3u8
    const [hfSegments, setHfSegments] = useState<HfSegment[]>([])
    // Segment[] format for findSegmentAt / no-video next-time logic
    const [segments, setSegments] = useState<Segment[]>([])

    const [liveSegments, setLiveSegments] = useState<HfSegment[]>([])
    const [hasAutoStarted, setHasAutoStarted] = useState(false)
    const [hfBucketUrl, setHfBucketUrl] = useState('')
    const [configLoaded, setConfigLoaded] = useState(false)

    const [videoState, setVideoState] = useState<VideoAreaState>({ type: 'loading' })
    const [playerTime, setPlayerTime] = useState<number | null>(null)
    const goingLiveRef = useRef(false)  // skip handleScrollEnd when triggered by goToLive's forceTime

    // Load config once — segments effect waits for this before deciding HF vs NVR
    useEffect(() => {
        fetchConfig().then(cfg => {
            setHfBucketUrl(cfg.hfBucketUrl || '')
        }).catch(() => {}).finally(() => {
            setConfigLoaded(true)
        })
    }, [])

    // === LIVE ===
    const goToLive = useCallback(() => {
        const today = getLocalDateString(new Date())
        if (selectedDate !== today) setSelectedDate(today)
        const liveUrl = `${window.location.origin}/recordings/ch${camId}/${today}/_live.m3u8`
        setVideoState({ type: 'live', url: getJellyJumpUrl(liveUrl) })
        setPlayerTime(null)
        goingLiveRef.current = true   // tell handleScrollEnd to ignore the next call
        setForceTime(getCurrentSeconds())
    }, [camId, selectedDate])

    // === LOAD DATES ===
    useEffect(() => {
        loadDates()
    }, [camId])

    async function loadDates() {
        try {
            const data = await fetchDates(camId)
            setDates(data.dates || [])
            if (data.dates?.length > 0) setSelectedDate(data.dates[0])
        } catch (err) {
            console.error('Failed to load dates:', err)
        }
    }

    // Fetch _live.m3u8 and refresh every 15s while in live mode (for timeupdate conversion)
    useEffect(() => {
        if (videoState.type !== 'live' || !selectedDate) return
        let isMounted = true
        const load = () => fetchLiveSegments(camId, selectedDate)
            .then(segs => { if (isMounted) setLiveSegments(segs) })
            .catch(() => {})
        load()
        const id = window.setInterval(load, 15000)
        return () => { isMounted = false; clearInterval(id) }
    }, [videoState.type, camId, selectedDate])

    // Ref so the segments effect can always call latest goToLive without being in deps
    const goToLiveRef = useRef(goToLive)
    useEffect(() => { goToLiveRef.current = goToLive })

    // === LOAD SEGMENTS ===
    // If HF is configured: parse HF playlist.m3u8 (no NVR API call needed).
    // If not: fall back to NVR API segments.
    useEffect(() => {
        if (!selectedDate || !configLoaded) return

        let isMounted = true

        async function load() {
            try {
                let segs: Segment[]
                let hfSegs: HfSegment[] = []

                if (hfBucketUrl) {
                    hfSegs = await fetchHfSegments(hfBucketUrl, camId, selectedDate)
                    segs = hfSegs.map(s => ({ time: secondsToHMS(s.wallClock), duration: s.duration }))
                } else {
                    const data = await fetchSegments(camId, selectedDate)
                    segs = data.segments || []
                }

                if (isMounted) {
                    setHfSegments(hfSegs)
                    setSegments(segs)

                    if (!hasAutoStarted && segs.length > 0) {
                        setHasAutoStarted(true)
                        goToLiveRef.current()
                    }
                }
            } catch (err) {
                console.error('Failed to load segments:', err)
                if (isMounted) { setHfSegments([]); setSegments([]) }
            }
        }

        load()

        const today = getLocalDateString(new Date())
        let intervalId: number | null = null
        if (selectedDate === today) {
            intervalId = window.setInterval(load, 15000)
        }

        return () => {
            isMounted = false
            if (intervalId) clearInterval(intervalId)
        }
    }, [camId, selectedDate, hasAutoStarted, hfBucketUrl, configLoaded])

    // === HANDLERS ===

    function handleScrollStart() {
        setVideoState({ type: 'loading' })
        setPlayerTime(null)
    }

    function handleScrollEnd(time: number) {
        if (goingLiveRef.current) {
            goingLiveRef.current = false
            return
        }
        const segment = findSegmentAt(time, segments)

        if (!segment) {
            const nextSeg = segments.find(seg => parseTime(seg.time) > time)
            setVideoState({ type: 'no-video', nextTime: nextSeg ? parseTime(nextSeg.time) : null })
            return
        }

        if (hfBucketUrl) {
            const offset = wallClockToOffset(time, hfSegments)
            const hfUrl = getHfPlaylistUrl(hfBucketUrl, camId, selectedDate)
            setVideoState({ type: 'vod', url: getJellyJumpHfUrlWithSeek(hfUrl, offset) })
        } else {
            const url = getPlaylistUrl(camId, selectedDate, segment.time)
            setVideoState({ type: 'vod', url: getJellyJumpUrl(window.location.origin + url) })
        }

        setPlayerTime(null)
    }

    // JellyJump sends currentTime as Unix timestamp (seconds since epoch) when the
    // HLS playlist has EXT-X-PROGRAM-DATE-TIME tags (ffmpeg -hls_flags program_date_time).
    // Anything > 86400 can't be a same-day offset — extract wall-clock time-of-day directly.
    function handleVideoTimeUpdate(time: number) {
        if (time > 86400) {
            const d = new Date(time * 1000)
            setPlayerTime(d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds())
        } else if (videoState.type === 'live' && liveSegments.length > 0) {
            setPlayerTime(offsetToWallClock(time, liveSegments))
        } else if (hfSegments.length > 0) {
            setPlayerTime(offsetToWallClock(time, hfSegments))
        } else {
            setPlayerTime(time)
        }
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

    function formatTimeHMS(seconds: number): string {
        return secondsToHMS(seconds)
    }

    const segmentStartTime = (videoState.type === 'vod' || videoState.type === 'live') ? 0 : null

    // === RENDER ===
    return (
        <div className="expanded-view">
            <div className="video-stage">
                <div className="camera-badge">📹 CH{camId}</div>

                {videoState.type === 'live' && (
                    <VideoPlayer
                        url={videoState.url}
                        onTimeUpdate={handleVideoTimeUpdate}
                    />
                )}

                {videoState.type === 'vod' && (
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
                        onGoLive={goToLive}
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
                    onGoLive={goToLive}
                    externalForceTime={forceTime}
                    segmentStartTime={segmentStartTime}
                    playerTime={playerTime}
                />
            )}
        </div>
    )
}

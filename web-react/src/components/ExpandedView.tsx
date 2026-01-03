import { useState, useEffect } from 'react'
import { Channel, fetchDates } from '../services/api'
import { getWebRTCUrl } from '../services/go2rtc'
import TimeScroller from './TimeScroller'
import './ExpandedView.css'

interface ExpandedViewProps {
    camId: string
    channels: Record<string, Channel>
}

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [hlsUrl, setHlsUrl] = useState<string | null>(null)

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

    const [playbackTime, setPlaybackTime] = useState<number | null>(null)

    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            // Security check: ensure message comes from expected origin (same origin for now)
            if (event.origin !== window.location.origin) return;

            if (event.data && event.data.type === 'timeupdate') {
                // Player sends relative time (seconds from start of video)
                // Assuming the player plays a single file or a playlist that knows its absolute time?
                // Actually, for HLS playlist playback, HLS.js usually reports time relative to the start of the playlist/segment.
                // But our 'playlist.m3u8' is constructed for the WHOLE DAY (or range).
                // So if the playlist starts at 00:00:00 (which it doesn't, it starts at the first segment), 
                // we need to know the ABSOLUTE time.

                // However, `Player.js` (JellyJump) wraps HLS.js. 
                // For now, let's assume the player sends the ABSOLUTE time of day in seconds.
                // If it sends relative time, we might need to adjust. 
                // But typically for CCTV playback, we want absolute timestamps.

                if (typeof event.data.currentTime === 'number') {
                    setPlaybackTime(event.data.currentTime)
                }
            }
        }

        window.addEventListener('message', handleMessage)
        return () => window.removeEventListener('message', handleMessage)
    }, [])

    function playLive() {
        setHlsUrl(null)
        setPlaybackTime(null)
        // Switch to today/latest date when going live
        if (dates.length > 0) {
            setSelectedDate(dates[0])
        }
    }

    // Handler for TimeScroller - plays HLS at a specific time
    function handlePlayHls(url: string) {
        setHlsUrl(url)
    }

    function getVideoSrc(): string {
        // If playing from TimeScroller
        if (hlsUrl) {
            return hlsUrl
        }

        // Default: go2rtc WebRTC stream for LIVE
        return getWebRTCUrl(camId)
    }

    const videoSrc = getVideoSrc()
    const isLive = !hlsUrl

    return (
        <div className="expanded-view">
            <div className="player-header">
                <h2>Camera {camId}</h2>
            </div>

            <div className="video-stage">
                {videoSrc ? (
                    <iframe
                        src={videoSrc}
                        allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
                        className="video-player"
                    />
                ) : (
                    <div className="video-placeholder">Select a recording</div>
                )}
            </div>

            {/* Time Scroller for HLS seeking */}
            {selectedDate && (
                <TimeScroller
                    camId={camId}
                    date={selectedDate}
                    availableDates={dates}
                    onDateChange={setSelectedDate}
                    isLive={isLive}
                    playbackTime={playbackTime}
                    onPlayHls={handlePlayHls}
                    onPlayLive={playLive}
                />
            )}
        </div>
    )
}

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

    function playLive() {
        setHlsUrl(null)
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
                <div className="controls-row">
                    <select
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                    >
                        {dates.map(date => (
                            <option key={date} value={date}>{date}</option>
                        ))}
                    </select>
                </div>
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
                    isLive={isLive}
                    onPlayHls={handlePlayHls}
                    onPlayLive={playLive}
                />
            )}
        </div>
    )
}

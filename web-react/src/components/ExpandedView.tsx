import { useState, useEffect } from 'react'
import { Channel, fetchDates, fetchRecordings, Recording } from '../services/api'
import { getWebRTCUrl, getHlsApiUrl, getJellyJumpUrl, isMobile } from '../services/go2rtc'
import Timeline from './Timeline'
import TimeScroller from './TimeScroller'
import Playlist from './Playlist'
import './ExpandedView.css'

interface ExpandedViewProps {
    camId: string
    channels: Record<string, Channel>
}

export default function ExpandedView({ camId, channels: _channels }: ExpandedViewProps) {
    const [dates, setDates] = useState<string[]>([])
    const [selectedDate, setSelectedDate] = useState('')
    const [recordings, setRecordings] = useState<Recording[]>([])
    const [currentIndex, setCurrentIndex] = useState(-1)
    const [isLive, setIsLive] = useState(true)
    const [hlsUrl, setHlsUrl] = useState<string | null>(null)  // For TimeScroller playback

    useEffect(() => {
        loadDates()
    }, [camId])

    useEffect(() => {
        if (selectedDate) {
            loadRecordings()
        }
    }, [selectedDate])

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

    async function loadRecordings() {
        try {
            const data = await fetchRecordings(camId, selectedDate)
            setRecordings(data.recordings || [])
        } catch (err) {
            console.error('Failed to load recordings:', err)
        }
    }

    function playLive() {
        setIsLive(true)
        setCurrentIndex(-1)
        setHlsUrl(null)
    }

    function playClip(index: number) {
        const rec = recordings[index]
        if (!rec) return

        // For LIVE segment on MOBILE: auto-play via WebRTC directly
        if (rec.live && isMobile()) {
            playLive()
            return
        }

        setIsLive(false)
        setCurrentIndex(index)
        setHlsUrl(null)
    }

    // Handler for TimeScroller - plays HLS at a specific time
    function handlePlayHls(url: string) {
        setIsLive(false)
        setCurrentIndex(-1)
        setHlsUrl(url)
    }

    /**
     * Get the iframe source URL for the current video
     */
    function getVideoSrc(): string {
        // If playing from TimeScroller
        if (hlsUrl) {
            return hlsUrl
        }

        if (isLive) {
            // go2rtc WebRTC stream for LIVE
            return getWebRTCUrl(camId)
        }

        const rec = recordings[currentIndex]
        if (!rec) return ''

        // Handle Cloud Only recordings
        if (rec.size === 'Cloud Only') {
            if (rec.youtube_url) {
                try {
                    const urlObj = new URL(rec.youtube_url)
                    const videoId = urlObj.searchParams.get('v')
                    if (videoId) {
                        return `https://www.youtube.com/embed/${videoId}?autoplay=1`
                    }
                } catch (e) {
                    console.error('Invalid YouTube URL', rec.youtube_url)
                }
            }
            return ''
        }

        // For LIVE recording segment
        if (rec.live) {
            // On mobile, use WebRTC directly for better performance
            if (isMobile()) {
                return getWebRTCUrl(camId)
            }
            // On desktop, use HLS via JellyJump
            const hlsApiUrl = getHlsApiUrl(camId)
            return getJellyJumpUrl(hlsApiUrl)
        }

        // For local recordings, use JellyJump embed
        const recordingUrl = `${window.location.origin}/recordings/${rec.name}`
        return getJellyJumpUrl(recordingUrl)
    }

    const videoSrc = getVideoSrc()

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
                    <button className="btn btn-live" onClick={playLive}>
                        Live
                    </button>
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

            {/* New Time Scroller for HLS seeking */}
            {selectedDate && (
                <TimeScroller
                    camId={camId}
                    date={selectedDate}
                    onPlayHls={handlePlayHls}
                    onPlayLive={playLive}
                />
            )}

            <Timeline
                recordings={recordings}
                currentIndex={currentIndex}
                onPlayClip={playClip}
            />

            <Playlist
                recordings={recordings}
                currentIndex={currentIndex}
                onPlayClip={playClip}
            />
        </div>
    )
}


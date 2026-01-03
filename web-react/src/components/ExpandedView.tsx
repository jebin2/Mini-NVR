import { useState, useEffect } from 'react'
import { Channel, fetchDates, fetchRecordings, Recording } from '../services/api'
import { getWebRTCUrl } from '../services/go2rtc'
import Timeline from './Timeline'
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
    }

    function playClip(index: number) {
        setIsLive(false)
        setCurrentIndex(index)
    }

    const videoSrc = isLive
        ? getWebRTCUrl(camId)
        : recordings[currentIndex]?.name
            ? `/recordings/${recordings[currentIndex].name}`
            : ''

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
                        🔴 Live (WebRTC)
                    </button>
                </div>
            </div>

            <div className="video-stage">
                {isLive ? (
                    <iframe
                        src={videoSrc}
                        allow="autoplay; fullscreen"
                        className="video-player"
                    />
                ) : videoSrc ? (
                    <video
                        src={videoSrc}
                        controls
                        autoPlay
                        className="video-player"
                    />
                ) : (
                    <div className="video-placeholder">Select a recording</div>
                )}
            </div>

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

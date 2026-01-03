import { Recording } from '../services/api'
import './Timeline.css'

interface TimelineProps {
    recordings: Recording[]
    currentIndex: number
    onPlayClip: (index: number) => void
}

const SECONDS_IN_DAY = 86400

function parseTime(timeStr: string): number {
    const parts = timeStr.split(':')
    return (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2] || 0)
}

export default function Timeline({ recordings, currentIndex, onPlayClip }: TimelineProps) {
    return (
        <div className="timeline-wrapper">
            <div className="timeline-track">
                {recordings.map((rec, index) => {
                    const startSec = parseTime(rec.startTime)
                    const duration = rec.duration || 600
                    const leftPct = (startSec / SECONDS_IN_DAY) * 100
                    const widthPct = (duration / SECONDS_IN_DAY) * 100
                    const isCloud = rec.size === 'Cloud Only'
                    const isActive = index === currentIndex

                    return (
                        <div
                            key={index}
                            className={`timeline-segment ${rec.live ? 'live' : ''} ${isCloud ? 'cloud' : ''} ${isActive ? 'active' : ''}`}
                            style={{
                                left: `${leftPct}%`,
                                width: `${Math.max(widthPct, 0.2)}%`,
                            }}
                            title={`${rec.startTime} (${rec.size})`}
                            onClick={() => onPlayClip(index)}
                        />
                    )
                })}
            </div>
            <div className="time-labels">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>23:59</span>
            </div>
        </div>
    )
}

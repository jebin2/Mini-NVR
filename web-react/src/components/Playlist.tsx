import { Recording } from '../services/api'
import { fmtDuration } from '../services/utils'
import './Playlist.css'

interface PlaylistProps {
    recordings: Recording[]
    currentIndex: number
    onPlayClip: (index: number) => void
}

export default function Playlist({ recordings, currentIndex, onPlayClip }: PlaylistProps) {
    // Show newest first
    const reversed = [...recordings].reverse()

    return (
        <div className="playlist">
            {reversed.map((rec, reversedIndex) => {
                const originalIndex = recordings.length - 1 - reversedIndex
                const isActive = originalIndex === currentIndex
                const durStr = fmtDuration(rec.duration)
                const isCloud = rec.size === 'Cloud Only'

                return (
                    <div
                        key={originalIndex}
                        className={`clip-card ${isActive ? 'active' : ''}`}
                        onClick={() => onPlayClip(originalIndex)}
                    >
                        <div className="clip-main">
                            <div className="clip-time">{rec.startTime}</div>
                            <div className="clip-meta">
                                {rec.size} {durStr ? `• ${durStr}` : ''}
                                {rec.live && <span className="live-badge">● LIVE</span>}
                            </div>
                        </div>

                        <div className="clip-actions">
                            {!rec.live && !isCloud && (
                                <a
                                    href={`/recordings/${rec.name}`}
                                    download={rec.name.split('/').pop()}
                                    className="clip-btn"
                                    title="Download"
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    ⬇
                                </a>
                            )}
                            {rec.youtube_url && (
                                <>
                                    <button
                                        className="clip-btn"
                                        title="Copy YouTube Link"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            navigator.clipboard.writeText(rec.youtube_url!)
                                        }}
                                    >
                                        📋
                                    </button>
                                    <a
                                        href={rec.youtube_url}
                                        target="_blank"
                                        className="clip-btn youtube"
                                        title="Watch on YouTube"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        ▶
                                    </a>
                                </>
                            )}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

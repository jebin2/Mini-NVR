import { Channel } from '../services/api'
import { getSnapshotUrl } from '../services/go2rtc'
import './CameraGrid.css'

interface CameraGridProps {
    channels: Record<string, Channel>
    onOpenCamera: (camId: string) => void
}

export default function CameraGrid({ channels, onOpenCamera }: CameraGridProps) {
    const channelIds = Object.keys(channels)

    if (channelIds.length === 0) {
        return (
            <div className="grid-empty">
                <p>No cameras available</p>
            </div>
        )
    }

    return (
        <div className="grid-container">
            {channelIds.map(camId => {
                const cam = channels[camId]
                const isLive = cam.status === 'LIVE'
                const badgeClass = isLive ? 'live' : cam.status === 'REC' ? 'rec' : 'off'

                return (
                    <div
                        key={camId}
                        className="cam-card"
                        onClick={() => onOpenCamera(camId)}
                    >
                        <div className="cam-overlay">
                            <span className={`badge ${badgeClass}`}>● {cam.status}</span>
                            <span className="badge">CH {camId}</span>
                        </div>
                        <img
                            className="cam-preview"
                            src={getSnapshotUrl(camId)}
                            alt={`Camera ${camId}`}
                            onError={(e) => {
                                (e.target as HTMLImageElement).style.display = 'none';
                                (e.target as HTMLImageElement).nextElementSibling?.setAttribute('style', 'display: flex');
                            }}
                        />
                        <div className="cam-placeholder" style={{ display: 'none' }}>
                            <span className="cam-icon">📹</span>
                            <span className="cam-label">Camera {camId}</span>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

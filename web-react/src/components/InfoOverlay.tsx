import './InfoOverlay.css'

type OverlayType = 'loading' | 'no-video' | 'error'

interface InfoOverlayProps {
    type: OverlayType
    message?: string
    onRetry?: () => void
    onGoNext?: () => void
    nextTime?: string | null
    onGoLive?: () => void
}

/**
 * Info overlay shown when video player is not displayed.
 * Handles loading, no-video, and error states.
 */
export default function InfoOverlay({
    type,
    message,
    onRetry,
    onGoNext,
    nextTime,
    onGoLive
}: InfoOverlayProps) {
    return (
        <div className={`info-overlay info-overlay--${type}`}>
            <div className="info-overlay__content">
                {type === 'loading' && (
                    <>
                        <div className="info-overlay__spinner" />
                        <p className="info-overlay__message">{message || 'Loading...'}</p>
                    </>
                )}

                {type === 'no-video' && (
                    <>
                        <span className="info-overlay__icon">🚫</span>
                        <h3>No Video Available</h3>
                        <p className="info-overlay__message">{message || 'No recording at this time'}</p>

                        {onGoNext && nextTime && (
                            <button className="info-overlay__btn" onClick={onGoNext}>
                                ⏭ Go to Next ({nextTime})
                            </button>
                        )}

                        {onGoLive && (
                            <button className="info-overlay__btn info-overlay__btn--live" onClick={onGoLive}>
                                📺 Go Live
                            </button>
                        )}
                    </>
                )}

                {type === 'error' && (
                    <>
                        <span className="info-overlay__icon">⚠️</span>
                        <h3>Error</h3>
                        <p className="info-overlay__message">{message || 'Failed to load video'}</p>

                        {onRetry && (
                            <button className="info-overlay__btn" onClick={onRetry}>
                                🔄 Retry
                            </button>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}

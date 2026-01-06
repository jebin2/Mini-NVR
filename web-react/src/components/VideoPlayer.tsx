import { useEffect, useRef } from 'react'
import './VideoPlayer.css'

interface VideoPlayerProps {
    url: string
    onTimeUpdate?: (time: number) => void
}

/**
 * Self-contained video player component.
 * Renders an iframe and listens for timeupdate messages from the player.
 * When unmounted, all callbacks stop automatically.
 */
export default function VideoPlayer({ url, onTimeUpdate }: VideoPlayerProps) {
    const timeUpdateRef = useRef(onTimeUpdate)
    timeUpdateRef.current = onTimeUpdate

    useEffect(() => {
        const handleMessage = (event: MessageEvent) => {
            // Only accept messages from allowed origins
            const allowedOrigins = [
                window.location.origin,
                'https://www.voidall.com',
                'https://cctv.voidall.com'
            ]
            if (!allowedOrigins.includes(event.origin)) return

            if (event.data?.type === 'timeupdate' && typeof event.data.currentTime === 'number') {
                timeUpdateRef.current?.(event.data.currentTime)
            }
        }

        window.addEventListener('message', handleMessage)
        return () => window.removeEventListener('message', handleMessage)
    }, [])

    return (
        <iframe
            src={url}
            allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
            className="video-player-iframe"
        />
    )
}

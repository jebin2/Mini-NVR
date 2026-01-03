/**
 * go2rtc Service
 * Ported from web/js/go2rtc.js
 */



export function getSnapshotUrl(camId: string): string {
    return `/api/go2rtc/api/frame.jpeg?src=cam${camId}&t=${Date.now()}`
}

export function getWebRTCUrl(camId: string): string {
    return `/api/go2rtc/webrtc.html?src=cam${camId}`
}

export function getHLSUrl(camId: string): string {
    return `/api/go2rtc/hls.html?src=cam${camId}`
}

export function getMSEUrl(camId: string): string {
    return `/api/go2rtc/mse.html?src=cam${camId}`
}

export function getSnapshotRefreshInterval(): number {
    // Slower refresh on mobile for performance
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent)
    return isMobile ? 5000 : 2000
}

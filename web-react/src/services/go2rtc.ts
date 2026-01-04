/**
 * go2rtc Service
 * Ported from web-vanilla/js/go2rtc.js
 */

/**
 * Get the base URL for go2rtc API (proxied through Mini-NVR for auth)
 */
export function getBaseUrl(): string {
    return `${window.location.origin}/api/go2rtc`
}

/**
 * Detect if running on a mobile device
 */
export function isMobile(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
        || window.innerWidth < 768
}

/**
 * Get snapshot URL for grid preview
 */
export function getSnapshotUrl(camId: string): string {
    return `${getBaseUrl()}/api/frame.jpeg?src=cam${camId}&t=${Date.now()}`
}

/**
 * Get the WebRTC stream URL for go2rtc embedded player (for LIVE)
 */
export function getWebRTCUrl(camId: string): string {
    const suffix = isMobile() ? '_mobile' : ''
    return `${getBaseUrl()}/stream.html?src=cam${camId}${suffix}`
}

/**
 * Get the HLS API URL for a camera (for usage in JellyJump)
 * HLS is usually for recording playback, but if used for live, we could optimize too.
 * For now, we keep HLS as is (likely used for recordings).
 */
export function getHlsApiUrl(camId: string): string {
    return `${getBaseUrl()}/api/stream.m3u8?src=cam${camId}`
}

/**
 * Get the HLS player page URL
 */
export function getHLSUrl(camId: string): string {
    return `${getBaseUrl()}/hls.html?src=cam${camId}`
}

/**
 * Get the MSE player page URL
 */
export function getMSEUrl(camId: string): string {
    const suffix = isMobile() ? '_mobile' : ''
    return `${getBaseUrl()}/mse.html?src=cam${camId}${suffix}`
}

/**
 * Get snapshot refresh interval (longer on mobile for better performance)
 */
export function getSnapshotRefreshInterval(): number {
    return isMobile() ? 10000 : 2000  // 10 seconds on mobile, 2 seconds on desktop
}

/**
 * Build JellyJump embed URL for video playback
 * @param videoUrl - URL of the video to play (recording URL or HLS URL)
 */
export function getJellyJumpUrl(videoUrl: string): string {
    const baseUrl = 'https://www.voidall.com/JellyJump/embed.html'
    const controls = 'none'
    return `${baseUrl}?video_url=${encodeURIComponent(videoUrl)}&controls=${controls}&credentials=true`
}

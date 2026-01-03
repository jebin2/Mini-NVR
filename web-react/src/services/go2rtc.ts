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
    let url = `${getBaseUrl()}/api/frame.jpeg?src=cam${camId}`

    // Reduce image size on mobile for faster loading
    if (isMobile()) {
        url += `&width=720`
    }

    url += `&t=${Date.now()}`
    return url
}

/**
 * Get the WebRTC stream URL for go2rtc embedded player (for LIVE)
 */
export function getWebRTCUrl(camId: string): string {
    return `${getBaseUrl()}/stream.html?src=cam${camId}`
}

/**
 * Get the HLS API URL for a camera (for usage in JellyJump)
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
    return `${getBaseUrl()}/mse.html?src=cam${camId}`
}

/**
 * Get snapshot refresh interval (longer on mobile for better performance)
 */
export function getSnapshotRefreshInterval(): number {
    return isMobile() ? 60000 : 10000  // 1 minute on mobile, 10 seconds on desktop
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

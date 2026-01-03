/**
 * go2rtc integration module
 * Centralizes all go2rtc URL building and streaming helpers
 */

/**
 * Get the go2rtc host (same as current page hostname)
 */
export function getHost() {
    return window.location.hostname;
}

/**
 * Get the base URL for go2rtc API (proxied through Mini-NVR for auth)
 */
export function getBaseUrl() {
    // Route through Mini-NVR for authentication
    return `${window.location.origin}/api/go2rtc`;
}

/**
 * Get the WebRTC stream URL for a camera
 * @param {number|string} camId - Camera ID
 */
export function getStreamUrl(camId) {
    return `${getBaseUrl()}/stream.html?src=cam${camId}`;
}

/**
 * Get the HLS stream URL for a camera (for usage in JellyJump)
 * @param {number|string} camId - Camera ID
 */
export function getHlsUrl(camId) {
    return `${getBaseUrl()}/api/stream.m3u8?src=cam${camId}`;
}

/**
 * Detect if running on a mobile device
 */
export function isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
        || window.innerWidth < 768;
}

/**
 * Get the snapshot refresh interval (longer on mobile for better performance)
 */
export function getSnapshotRefreshInterval() {
    return isMobile() ? 1000 * 60 : 1000 * 10;  // 1 minute on mobile, 10 seconds on desktop
}

/**
 * Get a snapshot/frame URL for a camera
 * @param {number|string} camId - Camera ID
 * @param {boolean} bustCache - Add cache-busting timestamp (default: true)
 */
export function getSnapshotUrl(camId, bustCache = true) {
    let url = `${getBaseUrl()}/api/frame.jpeg?src=cam${camId}`;

    // Reduce image size on mobile for faster loading
    if (isMobile()) {
        url += `&width=720`;  // Increased resolution for better viewing
    }

    if (bustCache) {
        url += `&t=${Date.now()}`;
    }
    return url;
}

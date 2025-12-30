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
 * Get a snapshot/frame URL for a camera
 * @param {number|string} camId - Camera ID
 * @param {boolean} bustCache - Add cache-busting timestamp (default: true)
 */
export function getSnapshotUrl(camId, bustCache = true) {
    let url = `${getBaseUrl()}/api/frame.jpeg?src=cam${camId}`;
    if (bustCache) {
        url += `&t=${Date.now()}`;
    }
    return url;
}

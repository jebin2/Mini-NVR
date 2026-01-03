/**
 * Utility functions
 * Ported from web/js/utils.js
 */

export function fmtDuration(seconds?: number): string {
    if (!seconds || seconds <= 0) return ''

    const hrs = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)

    if (hrs > 0) {
        return `${hrs}h ${mins}m`
    } else if (mins > 0) {
        return `${mins}m ${secs}s`
    }
    return `${secs}s`
}

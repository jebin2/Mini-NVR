/**
 * HuggingFace HLS playlist parser.
 * Segments are named HHMMSS.ts so each filename encodes its wall-clock start time.
 * Builds a wall-clock ↔ playlist-offset map so we can seek by real time.
 */

export interface HfSegment {
    wallClock: number      // seconds from midnight (from HHMMSS.ts filename)
    playlistOffset: number // cumulative seconds into the VOD playlist
    duration: number
}

function parsePlaylistText(text: string): HfSegment[] {
    const segments: HfSegment[] = []
    const lines = text.split('\n')
    let playlistOffset = 0
    let pendingDuration: number | null = null

    for (const raw of lines) {
        const line = raw.trim()
        if (line.startsWith('#EXTINF:')) {
            pendingDuration = parseFloat(line.slice(8).split(',')[0])
        } else if (line.endsWith('.ts') && pendingDuration !== null) {
            const match = line.match(/(\d{2})(\d{2})(\d{2})\.ts$/)
            if (match) {
                const wallClock = parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseInt(match[3])
                segments.push({ wallClock, playlistOffset, duration: pendingDuration })
                playlistOffset += pendingDuration
            }
            pendingDuration = null
        }
    }

    return segments
}

export async function fetchHfSegments(hfBucketUrl: string, channel: string, date: string): Promise<HfSegment[]> {
    const url = `${hfBucketUrl}ch${channel}/${date}/playlist.m3u8`
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HF playlist fetch failed: ${res.status}`)
    return parsePlaylistText(await res.text())
}

/** Fetch and parse the live recording manifest from the NVR server. */
export async function fetchLiveSegments(channel: string, date: string): Promise<HfSegment[]> {
    const url = `/recordings/ch${channel}/${date}/_live.m3u8`
    const res = await fetch(url, { credentials: 'include' })
    if (!res.ok) throw new Error(`Live m3u8 fetch failed: ${res.status}`)
    return parsePlaylistText(await res.text())
}

/** Wall-clock seconds → playlist offset (seconds into the VOD). */
export function wallClockToOffset(wallClock: number, segments: HfSegment[]): number {
    if (segments.length === 0) return 0
    for (let i = segments.length - 1; i >= 0; i--) {
        if (wallClock >= segments[i].wallClock) {
            return segments[i].playlistOffset + Math.min(
                wallClock - segments[i].wallClock,
                segments[i].duration
            )
        }
    }
    return 0
}

/** Playlist offset (seconds into VOD) → wall-clock seconds. */
export function offsetToWallClock(offset: number, segments: HfSegment[]): number {
    if (segments.length === 0) return 0
    for (let i = segments.length - 1; i >= 0; i--) {
        if (offset >= segments[i].playlistOffset) {
            return segments[i].wallClock + (offset - segments[i].playlistOffset)
        }
    }
    return segments[0].wallClock
}

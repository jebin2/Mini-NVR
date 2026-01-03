/**
 * API Service
 * Ported from web/js/api.js
 */

const API_BASE = ''

export interface Channel {
    status: 'LIVE' | 'REC' | 'OFF'
}

export interface Recording {
    name: string
    startTime: string
    duration?: number
    size: string
    live?: boolean
    youtube_url?: string
}

function getCookie(name: string): string | undefined {
    const value = `; ${document.cookie}`
    const parts = value.split(`; ${name}=`)
    if (parts.length === 2) return parts.pop()?.split(';').shift()
}

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: HeadersInit = {
        'Accept': 'application/json',
        ...options.headers,
    }

    // Add CSRF Token for state-changing methods
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method || '')) {
        const token = getCookie('csrf_token')
        if (token) {
            (headers as Record<string, string>)['X-CSRF-Token'] = token
        }
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
        credentials: 'include',
    })

    if (res.status === 401) {
        window.location.href = '/'
        throw new Error('Unauthorized')
    }

    return res.json()
}

export async function fetchStorage(): Promise<{ summary: string }> {
    return fetchAPI('/api/storage')
}

export async function fetchLive(): Promise<{ channels: Record<string, Channel> }> {
    return fetchAPI('/api/live')
}

export async function fetchDates(channel: string): Promise<{ dates: string[] }> {
    return fetchAPI(`/api/dates?channel=${channel}`)
}

export async function fetchRecordings(channel: string, date: string): Promise<{ recordings: Recording[] }> {
    return fetchAPI(`/api/channel/${channel}/recordings?date=${date}`)
}

export async function logout(): Promise<void> {
    await fetchAPI('/api/logout', { method: 'POST' })
}

export async function deleteRecording(path: string): Promise<void> {
    await fetchAPI(`/api/recording?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
}

export async function restartYouTubeStream(): Promise<void> {
    await fetchAPI('/api/youtube/restart', { method: 'POST' })
}

// --- HLS Playback API ---

export interface Segment {
    time: string      // HH:MM:SS
    duration: number  // seconds
}

export interface SegmentsResponse {
    channel: number
    date: string
    segment_duration: number
    segments: Segment[]
}

/**
 * Get available HLS segments for a channel/date
 * Used to build the time scroll UI
 */
export async function fetchSegments(channel: string, date: string): Promise<SegmentsResponse> {
    return fetchAPI(`/api/playback/${channel}/${date}/segments`)
}

/**
 * Get the HLS playlist URL for a time range
 * @param channel Channel number
 * @param date Date in YYYY-MM-DD format
 * @param start Optional start time in HH:MM:SS format
 * @param end Optional end time in HH:MM:SS format
 */
export function getPlaylistUrl(channel: string, date: string, start?: string, end?: string): string {
    let url = `/api/playback/${channel}/${date}/playlist.m3u8`
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const queryStr = params.toString()
    if (queryStr) url += `?${queryStr}`
    return url
}

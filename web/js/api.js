import { CONFIG } from './config.js';

// Helper to read cookies
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

async function fetchAPI(endpoint, options = {}) {
    // Default headers
    const headers = {
        'Accept': 'application/json',
        ...options.headers
    };

    // Add CSRF Token for state-changing methods
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method)) {
        const token = getCookie('csrf_token');
        if (token) {
            headers['X-CSRF-Token'] = token;
        }
    }

    const config = {
        ...options,
        headers
    };

    const res = await fetch(`${CONFIG.apiBase}${endpoint}`, config);
    if (res.status === 401) {
        window.location.href = '/login.html';
        throw new Error("Unauthorized");
    }
    return await res.json();
}

export async function fetchStorage() {
    return await fetchAPI('/storage');
}

export async function fetchLive() {
    return await fetchAPI('/live');
}

export async function fetchDates(channel) {
    return await fetchAPI(`/dates?channel=${channel}`);
}

export async function fetchRecordings(channel, date) {
    return await fetchAPI(`/channel/${channel}/recordings?date=${date}`);
}

export async function logout() {
    await fetchAPI('/logout', { method: 'POST' });
    window.location.href = '/login.html';
}

export async function deleteRecording(path) {
    return await fetchAPI(`/recording?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
}

export async function restartYouTubeStream() {
    return await fetchAPI('/youtube/restart', { method: 'POST' });
}

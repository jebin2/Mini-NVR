import * as API from './api.js';
import * as UI from './ui.js';
import * as go2rtc from './go2rtc.js';
import { CONFIG } from './config.js';

let currentCam = 1;
let recordingsMap = [];
let currentPlayingIndex = -1;

let isLoggingOut = false;
let isStorageUpdating = false;
let isGridUpdating = false;

async function updateStorage() {
    if (isLoggingOut || isStorageUpdating) return;
    isStorageUpdating = true;
    try {
        const data = await API.fetchStorage();
        document.getElementById('storageDisplay').innerText = `💾 ${data.usedGB} / ${data.maxGB} GB`;
    } catch (e) { console.error(e); }
    finally { isStorageUpdating = false; }
}

async function updateGrid() {
    if (isLoggingOut || isGridUpdating) return;
    if (document.getElementById('gridView').classList.contains('hidden')) return;
    isGridUpdating = true;
    try {
        const data = await API.fetchLive();
        if (isLoggingOut) return; // check again
        UI.renderGrid(data.channels, openCamera);
    } catch (e) { console.error(e); }
    finally { isGridUpdating = false; }
}

async function openCamera(id) {
    currentCam = id;
    document.getElementById('activeCamTitle').innerText = `Camera ${id}`;
    toggleView('expanded');

    const data = await API.fetchDates(id);
    const sel = document.getElementById('dateSelect');
    sel.innerHTML = '';

    if (data.dates.length === 0) {
        const opt = document.createElement('option');
        opt.text = "No recordings";
        sel.add(opt);
    } else {
        data.dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.text = d;
            sel.add(opt);
        });
        loadRecordings();
    }
}

async function loadRecordings() {
    const date = document.getElementById('dateSelect').value;
    if (!date || date === "No recordings") return;

    const data = await API.fetchRecordings(currentCam, date);
    recordingsMap = data.recordings || [];

    UI.renderTimeline(recordingsMap, playClip);
    UI.renderPlaylist(recordingsMap, playClip, deleteClip);

    if (recordingsMap.length > 0) {
        playClip(recordingsMap.length - 1);
    }
}

async function deleteClip(index, path) {
    try {
        await API.deleteRecording(path);
        // Reload the recordings list
        loadRecordings();
    } catch (e) {
        alert('Failed to delete recording: ' + (e.message || 'Unknown error'));
    }
}

function playClip(index) {
    currentPlayingIndex = index;
    const rec = recordingsMap[index];
    if (!rec) return;

    // Handle Cloud Only
    if (rec.size === "Cloud Only") {
        if (rec.youtube_url) {
            // Extract Video ID
            let videoId = "";
            try {
                const urlObj = new URL(rec.youtube_url);
                videoId = urlObj.searchParams.get("v");
            } catch (e) {
                // Fallback for flat links if any
                console.error("Invalid YouTube URL", rec.youtube_url);
            }

            if (videoId) {
                const embedUrl = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
                const video = document.getElementById('mainPlayer');
                const container = video.parentElement;

                // Remove existing live/youtube frame
                const existingFrame = document.getElementById('liveFrame');
                if (existingFrame) existingFrame.remove();

                // Hide video, show iframe
                video.style.display = 'none';
                video.pause();

                const iframe = document.createElement('iframe');
                iframe.src = embedUrl;
                iframe.id = 'liveFrame'; // Reuse ID for easier cleanup
                iframe.style.cssText = 'width:100%; height:100%; border:none; background:#000;';
                iframe.allow = 'autoplay; encrypted-media; picture-in-picture';
                iframe.allowFullscreen = true;
                container.appendChild(iframe);

                UI.highlightClip(index);
                return;
            }
        }

        alert('This recording is deleted locally and has no YouTube link.');
        return;
    }

    const video = document.getElementById('mainPlayer');
    const container = video.parentElement;
    const existingFrame = document.getElementById('liveFrame');

    // Cleanup existing iframe
    if (existingFrame) existingFrame.remove();
    video.style.display = 'none';
    video.pause();

    // Build JellyJump URL
    // Use window.location.origin to get the full URL of the recording on the NVR server
    const recordingUrl = `${window.location.origin}/recordings/${rec.name}`;
    const baseUrl = 'https://www.voidall.com/JellyJump/embed.html';

    // Configure controls (minimal set + volume + screenshot)
    const controls = 'play,pause,volume,progress,time,fullscreen,speed,screenshot';

    // Construct full embed URL
    const embedUrl = `${baseUrl}?video_url=${encodeURIComponent(recordingUrl)}&controls=${controls}`;

    // Create and inject iframe
    const iframe = document.createElement('iframe');
    iframe.src = embedUrl;
    iframe.id = 'liveFrame'; // Reuse ID for easier cleanup logic
    iframe.style.cssText = 'width:100%; height:100%; border:none; background:#000;';
    iframe.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
    iframe.allowFullscreen = true;
    container.appendChild(iframe);

    UI.highlightClip(index);
}

function playLive() {
    const video = document.getElementById('mainPlayer');
    const container = video.parentElement;

    // Remove existing live frame if any
    const existingFrame = document.getElementById('liveFrame');
    if (existingFrame) {
        existingFrame.remove();
    }

    // go2rtc WebRTC stream URL
    const go2rtcUrl = go2rtc.getStreamUrl(currentCam);

    // Hide video element and show iframe
    video.pause();
    video.style.display = 'none';

    const iframe = document.createElement('iframe');
    iframe.src = go2rtcUrl;
    iframe.id = 'liveFrame';
    iframe.style.cssText = 'width:100%; height:100%; border:none; background:#000;';
    iframe.allow = 'autoplay';
    container.appendChild(iframe);

    // Highlight live clip if available
    const liveIndex = recordingsMap.findIndex(r => r.live);
    if (liveIndex >= 0) {
        UI.highlightClip(liveIndex);
    }
}

function handleTimelineClick(e) {
    const rect = e.target.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = x / rect.width;
    const daySeconds = 86400;
    const clickSeconds = pct * daySeconds;
    let closestIdx = -1;
    let minDiff = Infinity;

    recordingsMap.forEach((rec, i) => {
        const parts = rec.startTime.split(':');
        const startSec = (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2]);
        const diff = Math.abs(startSec - clickSeconds);
        if (diff < minDiff) {
            minDiff = diff;
            closestIdx = i;
        }
    });

    if (closestIdx !== -1) playClip(closestIdx);
}

async function handleLogout() {
    isLoggingOut = true;

    // Immediate UI Feedback
    document.getElementById('gridView').innerHTML = '';
    document.getElementById('expandedView').innerHTML = '';
    document.getElementById('storageDisplay').innerText = 'Logging out...';
    document.querySelector('.header-controls').style.opacity = '0.5';

    // Proceed with API call
    try {
        await API.logout();
    } catch (e) {
        // Force redirect if API fails
        window.location.href = '/login.html';
    }
}


function toggleView(view) {
    if (isLoggingOut) return;
    // ... rest of function ...
    const grid = document.getElementById('gridView');
    const expanded = document.getElementById('expandedView');
    const backBtn = document.getElementById('backBtn');

    if (view === 'expanded') {
        UI.stopGridRefresh();  // Stop refreshing snapshots
        grid.classList.add('hidden');
        grid.innerHTML = '';
        expanded.classList.add('active');
        backBtn.classList.remove('hidden');
    } else {
        // Remove live iframe if present
        const liveFrame = document.getElementById('liveFrame');
        if (liveFrame) {
            liveFrame.remove();
        }

        const player = document.getElementById('mainPlayer');
        if (player) {
            player.pause();
            player.src = '';
            player.style.display = '';  // Ensure video is visible
        }
        document.getElementById('dateSelect').innerHTML = '';
        document.getElementById('timeline').innerHTML = '';
        document.getElementById('playlist').innerHTML = '';
        recordingsMap = [];

        grid.classList.remove('hidden');
        expanded.classList.remove('active');
        backBtn.classList.add('hidden');

        // Show loading state while fetching
        grid.innerHTML = '<div style="color:#666;text-align:center;padding:50px 0;">Refreshing cameras...</div>';

        updateGrid();
    }
}

// ... handleTimelineClick ...

window.toggleView = toggleView;
window.playLive = playLive;
window.loadRecordings = loadRecordings;
window.handleTimelineClick = handleTimelineClick;

window.onload = () => {
    // Initial Loading State
    const grid = document.getElementById('gridView');
    if (grid) {
        grid.innerHTML = '<div style="color:#666;text-align:center;padding:50px 0;">Loading cameras...</div>';
    }

    updateStorage();
    updateGrid();
    // Increased intervals for better performance (especially on mobile)
    setInterval(updateGrid, 10000);  // 10 seconds
    setInterval(updateStorage, 30000);  // 30 seconds
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);


};

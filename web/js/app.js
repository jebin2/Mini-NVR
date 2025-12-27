import * as API from './api.js';
import * as UI from './ui.js';
import { CONFIG } from './config.js';

let currentCam = 1;
let recordingsMap = [];

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
    const rec = recordingsMap[index];
    if (!rec) return;

    const video = document.getElementById('mainPlayer');
    const liveFrame = document.getElementById('liveFrame');

    // Remove live iframe if present
    if (liveFrame) {
        liveFrame.remove();
        video.style.display = '';
    }

    video.src = `/recordings/${rec.name}`;
    video.play().catch(e => console.log("Autoplay blocked or format unsupported"));

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
    // Use the hostname from current URL, port 1984 for go2rtc API
    const go2rtcHost = window.location.hostname;
    const go2rtcUrl = `http://${go2rtcHost}:1984/stream.html?src=cam${currentCam}`;

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
    setInterval(updateGrid, CONFIG.gridRefreshInterval);
    setInterval(updateStorage, CONFIG.storageRefreshInterval);
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
};

import * as API from './api.js';
import * as UI from './ui.js';

let currentCam = 1;
let recordingsMap = [];

let isLoggingOut = false;

async function updateStorage() {
    if (isLoggingOut) return;
    try {
        const data = await API.fetchStorage();
        document.getElementById('storageDisplay').innerText = `💾 ${data.usedGB} / ${data.maxGB} GB`;
    } catch (e) { console.error(e); }
}

async function updateGrid() {
    if (isLoggingOut) return;
    if (document.getElementById('gridView').classList.contains('hidden')) return;
    try {
        const data = await API.fetchLive();
        if (isLoggingOut) return; // check again
        UI.renderGrid(data.channels, openCamera);
    } catch (e) { console.error(e); }
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
    UI.renderPlaylist(recordingsMap, playClip);

    if (recordingsMap.length > 0) {
        playClip(recordingsMap.length - 1);
    }
}

function playClip(index) {
    const rec = recordingsMap[index];
    if (!rec) return;

    const video = document.getElementById('mainPlayer');
    video.src = `/recordings/${rec.name}`;
    video.play().catch(e => console.log("Autoplay blocked or format unsupported"));

    UI.highlightClip(index);
}

function playLive() {
    const liveIndex = recordingsMap.findIndex(r => r.live);
    if (liveIndex >= 0) playClip(liveIndex);
    else alert("No live recording found for this channel right now.");
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
        grid.classList.add('hidden');
        grid.innerHTML = '';
        expanded.classList.add('active');
        backBtn.classList.remove('hidden');
    } else {
        const player = document.getElementById('mainPlayer');
        if (player) {
            player.pause();
            player.src = '';
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
    setInterval(updateGrid, 10000);
    setInterval(updateStorage, 60000);
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
};

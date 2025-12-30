import { fmtDuration } from './utils.js';
import * as go2rtc from './go2rtc.js';

// Store interval ID for cleanup
let gridRefreshInterval = null;

export function renderGrid(channels, onOpenCam) {
    const grid = document.getElementById('gridView');

    // Clear previous refresh interval
    if (gridRefreshInterval) {
        clearInterval(gridRefreshInterval);
        gridRefreshInterval = null;
    }

    // Clean up any existing video elements to free connections
    const existingVideos = grid.querySelectorAll('video');
    existingVideos.forEach(v => {
        v.pause();
        v.src = '';
        v.load();
    });

    grid.innerHTML = '';

    Object.keys(channels).forEach(chId => {
        const cam = channels[chId];
        const isLive = cam.status === 'LIVE';
        let badgeClass = 'off';
        if (isLive) badgeClass = 'live';
        else if (cam.status === 'REC') badgeClass = 'rec';

        const card = document.createElement('div');
        card.className = 'cam-card';
        card.onclick = () => onOpenCam(chId);

        // Use go2rtc snapshot for live preview
        const snapshotUrl = go2rtc.getSnapshotUrl(chId);

        card.innerHTML = `
            <div class="cam-overlay">
                <span class="badge ${badgeClass}">● ${cam.status}</span>
                <span class="badge">CH ${chId}</span>
            </div>
            <img class="cam-preview" data-cam="${chId}" src="${snapshotUrl}" alt="Camera ${chId}" 
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="cam-placeholder" style="display:none;">
                <span class="cam-icon">📹</span>
                <span class="cam-label">Camera ${chId}</span>
            </div>
        `;

        grid.appendChild(card);
    });

    // Refresh snapshots every 2 seconds for live preview effect
    gridRefreshInterval = setInterval(() => {
        const images = grid.querySelectorAll('.cam-preview');
        images.forEach(img => {
            const camId = img.dataset.cam;
            if (camId) {
                img.src = go2rtc.getSnapshotUrl(camId);
            }
        });
    }, 2000);
}

// Stop grid refresh when leaving grid view
export function stopGridRefresh() {
    if (gridRefreshInterval) {
        clearInterval(gridRefreshInterval);
        gridRefreshInterval = null;
    }
}

export function renderTimeline(recordings, onPlayClip) {
    const track = document.getElementById('timeline');
    track.innerHTML = '';
    const SECONDS_IN_DAY = 86400;

    recordings.forEach((rec, index) => {
        const parts = rec.startTime.split(':');
        const startSec = (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2]);
        const duration = rec.duration || 600;

        const leftPct = (startSec / SECONDS_IN_DAY) * 100;
        const widthPct = (duration / SECONDS_IN_DAY) * 100;

        const seg = document.createElement('div');
        const isCloud = rec.size === "Cloud Only";
        seg.className = `timeline-segment ${rec.live ? 'live' : ''} ${isCloud ? 'cloud' : ''}`;
        seg.style.left = `${leftPct}%`;
        seg.style.width = `${Math.max(widthPct, 0.2)}%`;
        seg.title = `${rec.startTime} (${rec.size})`;
        seg.onclick = (e) => {
            e.stopPropagation();
            onPlayClip(index);
        };
        track.appendChild(seg);
    });
}

export function renderPlaylist(recordings, onPlayClip, onDeleteClip) {
    const list = document.getElementById('playlist');
    list.innerHTML = '';

    for (let index = recordings.length - 1; index >= 0; index--) {
        const rec = recordings[index];
        const durStr = fmtDuration(rec.duration);

        const div = document.createElement('div');
        div.className = 'clip-card';
        div.id = `clip-${index}`;

        // Create main content area (clickable for playback)
        const mainContent = document.createElement('div');
        mainContent.className = 'clip-main';
        mainContent.onclick = () => onPlayClip(index);
        mainContent.innerHTML = `
            <div class="clip-time">${rec.startTime}</div>
            <div class="clip-meta">
                ${rec.size} ${durStr ? '• ' + durStr : ''}
                ${rec.live ? '<span style="color:var(--danger)"> ● LIVE</span>' : ''}
            </div>
        `;
        div.appendChild(mainContent);

        // Add action buttons for non-live recordings
        if (!rec.live) {
            const actions = document.createElement('div');
            actions.className = 'clip-actions';

            // Download button (Only if local)
            if (rec.size !== "Cloud Only") {
                const downloadBtn = document.createElement('a');
                downloadBtn.href = `/recordings/${rec.name}`;
                downloadBtn.download = rec.name.split('/').pop();
                downloadBtn.className = 'clip-btn download';
                downloadBtn.title = 'Download';
                downloadBtn.innerHTML = '⬇';
                downloadBtn.onclick = (e) => e.stopPropagation();
                actions.appendChild(downloadBtn);
            }

            // YouTube Button
            if (rec.youtube_url) {
                const ytBtn = document.createElement('a');
                ytBtn.href = rec.youtube_url;
                ytBtn.target = '_blank';
                ytBtn.className = 'clip-btn youtube';
                ytBtn.title = 'Watch on YouTube';
                ytBtn.innerHTML = '▶'; // Or use an SVG icon
                ytBtn.style.color = '#ff0000';
                ytBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (rec.size === "Cloud Only") {
                        e.preventDefault();
                        onPlayClip(index);
                    }
                };
                actions.appendChild(ytBtn);
            }

            // Delete button (Only if local)
            if (rec.size !== "Cloud Only") {
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'clip-btn delete';
                deleteBtn.title = 'Delete';
                deleteBtn.innerHTML = '🗑';
                deleteBtn.onclick = (e) => {
                    e.stopPropagation();
                    if (confirm(`Delete recording ${rec.startTime}?`)) {
                        onDeleteClip(index, rec.name);
                    }
                };
                actions.appendChild(deleteBtn);
            }

            div.appendChild(actions);
        }

        list.appendChild(div);
    }
}

export function highlightClip(index) {
    document.querySelectorAll('.clip-card').forEach(c => c.classList.remove('active'));
    const activeCard = document.getElementById(`clip-${index}`);
    if (activeCard) {
        activeCard.classList.add('active');
        activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
}

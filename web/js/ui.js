import { fmtDuration } from './utils.js';

export function renderGrid(channels, onOpenCam) {
    const grid = document.getElementById('gridView');

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

        const src = cam.file ? `/recordings/${cam.file}?t=${Date.now()}` : '';

        const card = document.createElement('div');
        card.className = 'cam-card';
        card.onclick = () => onOpenCam(chId);

        // Create placeholder instead of autoplay video to reduce connections
        card.innerHTML = `
        <div class="cam-overlay">
            <span class="badge ${badgeClass}">● ${cam.status}</span>
            <span class="badge">CH ${chId}</span>
        </div>
        <div class="cam-placeholder">
            <span class="cam-icon">📹</span>
            <span class="cam-label">Camera ${chId}</span>
        </div>
    `;

        // Lazy load video only on hover (reduces connection usage)
        if (src) {
            let videoLoaded = false;
            card.addEventListener('mouseenter', () => {
                if (videoLoaded) return;
                videoLoaded = true;
                const placeholder = card.querySelector('.cam-placeholder');
                const video = document.createElement('video');
                video.src = src;
                video.muted = true;
                video.autoplay = true;
                video.loop = true;
                video.playsInline = true;
                card.appendChild(video);
                if (placeholder) placeholder.style.display = 'none';
            });
        }

        grid.appendChild(card);
    });
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
        seg.className = `timeline-segment ${rec.live ? 'live' : ''}`;
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

            // Download button
            const downloadBtn = document.createElement('a');
            downloadBtn.href = `/recordings/${rec.name}`;
            downloadBtn.download = rec.name.split('/').pop();
            downloadBtn.className = 'clip-btn download';
            downloadBtn.title = 'Download';
            downloadBtn.innerHTML = '⬇';
            downloadBtn.onclick = (e) => e.stopPropagation();
            actions.appendChild(downloadBtn);

            // Delete button
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

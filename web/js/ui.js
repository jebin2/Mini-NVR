import { fmtDuration } from './utils.js';

export function renderGrid(channels, onOpenCam) {
    const grid = document.getElementById('gridView');
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

        card.innerHTML = `
        <div class="cam-overlay">
            <span class="badge ${badgeClass}">● ${cam.status}</span>
            <span class="badge">CH ${chId}</span>
        </div>
        ${src ? `<video src="${src}" muted autoplay loop playsinline></video>` : ''}
    `;
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

export function renderPlaylist(recordings, onPlayClip) {
    const list = document.getElementById('playlist');
    list.innerHTML = '';

    for (let index = recordings.length - 1; index >= 0; index--) {
        const rec = recordings[index];
        const durStr = fmtDuration(rec.duration);

        const div = document.createElement('div');
        div.className = 'clip-card';
        div.id = `clip-${index}`;
        div.onclick = () => onPlayClip(index);

        div.innerHTML = `
        <div class="clip-time">${rec.startTime}</div>
        <div class="clip-meta">
            ${rec.size} ${durStr ? '• ' + durStr : ''}
            ${rec.live ? '<span style="color:var(--danger)"> ● LIVE</span>' : ''}
        </div>
    `;
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

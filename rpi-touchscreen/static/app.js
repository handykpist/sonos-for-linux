// Sonos Touchscreen Controller Client
let currentState = null;
let currentTrackKey = "";
let currentLyrics = [];
let isSeeking = false;
let isAdjustingVolume = false;
let volumeDebounceTimer = null;

// DOM Elements
const digitalClock = document.getElementById("digital-clock");
const activeRoomLabel = document.getElementById("active-room-label");
const albumArt = document.getElementById("album-art");
const artPlaceholder = document.getElementById("art-placeholder");
const trackTitle = document.getElementById("track-title");
const trackArtist = document.getElementById("track-artist");
const trackAlbum = document.getElementById("track-album");
const timeElapsed = document.getElementById("time-elapsed");
const timeTotal = document.getElementById("time-total");
const progressFill = document.getElementById("progress-fill");
const progressTrack = document.getElementById("progress-track");
const waveformAnim = document.getElementById("waveform-anim");
const playIcon = document.getElementById("play-icon");
const pauseIcon = document.getElementById("pause-icon");
const volFill = document.getElementById("vol-fill");
const volPercent = document.getElementById("vol-percent");
const volTrack = document.getElementById("vol-track");

// Drawers & Modals
const roomModal = document.getElementById("room-modal");
const roomsList = document.getElementById("rooms-list");
const lyricsDrawer = document.getElementById("lyrics-drawer");
const lyricsLines = document.getElementById("lyrics-lines");
const favoritesDrawer = document.getElementById("favorites-drawer");
const favoritesGrid = document.getElementById("favorites-grid");
const nightDimmer = document.getElementById("night-dimmer");
const nightClock = document.getElementById("night-clock");
const nightDate = document.getElementById("night-date");
const nightTrackMini = document.getElementById("night-track-mini");

// 1. Clock Updates
function updateClock() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const timeStr = `${hours}:${minutes}`;
    if (digitalClock) digitalClock.textContent = timeStr;
    if (nightClock) nightClock.textContent = timeStr;
    if (nightDate) {
        nightDate.textContent = now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
    }
}
setInterval(updateClock, 1000);
updateClock();

// 2. Format Seconds -> MM:SS
function formatTime(secs) {
    if (isNaN(secs) || secs <= 0) return "0:00";
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// 3. State Polling & UI Update
async function pollState() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const state = await res.json();
        currentState = state;
        updateUI(state);
    } catch (e) {
        console.warn("Poll state error:", e);
    }
}

function updateUI(state) {
    // Room
    if (state.room) activeRoomLabel.textContent = state.room;

    // Track Meta
    trackTitle.textContent = state.title || "Ready to Play";
    trackArtist.textContent = state.artist || (state.room ? `Sonos in ${state.room}` : "Tap to select room");
    trackAlbum.textContent = state.album || "";

    // Artwork
    if (state.albumArt) {
        if (albumArt.src !== state.albumArt) {
            albumArt.src = state.albumArt;
        }
        albumArt.style.display = "block";
        artPlaceholder.style.display = "none";
    } else {
        albumArt.style.display = "none";
        artPlaceholder.style.display = "flex";
    }

    // Playback State (Play / Pause icons)
    const isPlaying = state.state === "PLAYING";
    if (isPlaying) {
        playIcon.style.display = "none";
        pauseIcon.style.display = "block";
        waveformAnim.style.opacity = "1";
    } else {
        playIcon.style.display = "block";
        pauseIcon.style.display = "none";
        waveformAnim.style.opacity = "0.2";
    }

    // Time Progress
    if (!isSeeking) {
        timeElapsed.textContent = formatTime(state.position);
        timeTotal.textContent = formatTime(state.duration);
        const pct = state.duration > 0 ? (state.position / state.duration) * 100 : 0;
        progressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }

    // Volume
    if (!isAdjustingVolume) {
        const v = state.volume || 0;
        volPercent.textContent = `${v}%`;
        volFill.style.width = `${v}%`;
    }

    // Night Mode track string
    if (nightTrackMini) {
        nightTrackMini.textContent = state.title ? `${isPlaying ? '▶' : '⏸'} ${state.title} — ${state.artist}` : "Sonos Idle";
    }

    // Lyrics fetch trigger on track change
    const newKey = `${state.title}_${state.artist}`;
    if (newKey !== currentTrackKey && state.title) {
        currentTrackKey = newKey;
        loadLyrics();
    }
}

// Client-side smooth time advance (60 FPS)
let lastFrameTime = performance.now();
function animLoop(now) {
    const dt = (now - lastFrameTime) / 1000.0;
    lastFrameTime = now;

    if (currentState && currentState.state === "PLAYING" && !isSeeking) {
        if (currentState.duration > 0 && currentState.position < currentState.duration) {
            currentState.position += dt;
            const pct = (currentState.position / currentState.duration) * 100;
            progressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
            timeElapsed.textContent = formatTime(currentState.position);
            updateLyricsHighlight(currentState.position);
        }
    }
    requestAnimationFrame(animLoop);
}
requestAnimationFrame(animLoop);

// 4. Playback Commands
async function postAction(endpoint, body = {}) {
    try {
        await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        setTimeout(pollState, 150);
    } catch (e) {
        console.error("Action failed:", endpoint, e);
    }
}

document.getElementById("btn-playpause").addEventListener("click", () => postAction("/api/playpause"));
document.getElementById("btn-next").addEventListener("click", () => postAction("/api/next"));
document.getElementById("btn-prev").addEventListener("click", () => postAction("/api/prev"));

// 5. Volume Controls & Debounce
function setVolumeDirect(vol) {
    vol = Math.max(0, Math.min(100, Math.round(vol)));
    volPercent.textContent = `${vol}%`;
    volFill.style.width = `${vol}%`;
    clearTimeout(volumeDebounceTimer);
    volumeDebounceTimer = setTimeout(() => {
        postAction("/api/volume", { volume: vol });
        isAdjustingVolume = false;
    }, 120);
}

document.getElementById("btn-vol-down").addEventListener("click", () => {
    isAdjustingVolume = true;
    const cur = currentState ? currentState.volume : 20;
    setVolumeDirect(cur - 3);
});

document.getElementById("btn-vol-up").addEventListener("click", () => {
    isAdjustingVolume = true;
    const cur = currentState ? currentState.volume : 20;
    setVolumeDirect(cur + 3);
});

document.getElementById("btn-mute").addEventListener("click", () => postAction("/api/mute"));

volTrack.addEventListener("click", (e) => {
    isAdjustingVolume = true;
    const rect = volTrack.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = (clickX / rect.width) * 100;
    setVolumeDirect(pct);
});

// 6. Scrub Seek
progressTrack.addEventListener("click", (e) => {
    if (!currentState || !currentState.duration) return;
    const rect = progressTrack.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    const targetSecs = pct * currentState.duration;
    isSeeking = true;
    progressFill.style.width = `${pct * 100}%`;
    timeElapsed.textContent = formatTime(targetSecs);
    postAction("/api/seek", { position: targetSecs }).then(() => {
        setTimeout(() => { isSeeking = false; }, 300);
    });
});

// 7. Room Selector Modal
document.getElementById("btn-room-select").addEventListener("click", async () => {
    try {
        const res = await fetch("/api/speakers");
        const data = await res.json();
        roomsList.innerHTML = "";
        data.speakers.forEach(spk => {
            const item = document.createElement("div");
            item.className = `room-item ${spk.active ? 'active' : ''}`;
            item.innerHTML = `
                <span>${spk.name}</span>
                <span style="font-size: 13px; color: ${spk.active ? '#38bdf8' : '#64748b'}">${spk.active ? 'Active' : 'Switch'}</span>
            `;
            item.addEventListener("click", () => {
                postAction("/api/speaker", { room: spk.name });
                roomModal.classList.remove("open");
            });
            roomsList.appendChild(item);
        });
        roomModal.classList.add("open");
    } catch (e) {
        console.error("Could not fetch speakers:", e);
    }
});

document.getElementById("btn-close-room-modal").addEventListener("click", () => {
    roomModal.classList.remove("open");
});

// 8. Sonos Radio & Favorites Drawer
document.getElementById("btn-favorites-toggle").addEventListener("click", async () => {
    favoritesDrawer.classList.add("open");
    try {
        const res = await fetch("/api/favorites");
        const data = await res.json();
        favoritesGrid.innerHTML = "";
        if (!data.favorites || data.favorites.length === 0) {
            favoritesGrid.innerHTML = "<p class='lyrics-notice'>No Sonos favorites found.</p>";
            return;
        }
        data.favorites.forEach(fav => {
            const card = document.createElement("div");
            card.className = "favorite-card";
            card.innerHTML = `
                <img class="fav-art" src="${fav.art || ''}" onerror="this.style.display='none'">
                <div class="fav-title">${fav.title}</div>
            `;
            card.addEventListener("click", () => {
                postAction("/api/favorite/play", { uri: fav.uri, meta: fav.meta });
                favoritesDrawer.classList.remove("open");
            });
            favoritesGrid.appendChild(card);
        });
    } catch (e) {
        favoritesGrid.innerHTML = "<p class='lyrics-notice'>Error loading favorites.</p>";
    }
});

document.getElementById("btn-close-favorites").addEventListener("click", () => {
    favoritesDrawer.classList.remove("open");
});

// 9. Synchronized Lyrics Drawer
document.getElementById("btn-lyrics-toggle").addEventListener("click", () => {
    lyricsDrawer.classList.add("open");
    if (currentLyrics.length === 0) loadLyrics();
});

document.getElementById("btn-close-lyrics").addEventListener("click", () => {
    lyricsDrawer.classList.remove("open");
});

async function loadLyrics() {
    lyricsLines.innerHTML = "<p class='lyrics-notice'>Searching lyrics...</p>";
    try {
        const res = await fetch("/api/lyrics");
        const data = await res.json();
        currentLyrics = data.lines || [];
        if (currentLyrics.length === 0) {
            lyricsLines.innerHTML = "<p class='lyrics-notice'>No lyrics found for this song.</p>";
            return;
        }
        lyricsLines.innerHTML = "";
        currentLyrics.forEach((line, idx) => {
            const p = document.createElement("div");
            p.className = "lyric-line";
            p.id = `lyric-line-${idx}`;
            p.textContent = line.text;
            lyricsLines.appendChild(p);
        });
    } catch (e) {
        lyricsLines.innerHTML = "<p class='lyrics-notice'>Could not load lyrics.</p>";
    }
}

function updateLyricsHighlight(curTime) {
    if (!currentLyrics || currentLyrics.length === 0 || !lyricsDrawer.classList.contains("open")) return;
    let activeIdx = -1;
    for (let i = 0; i < currentLyrics.length; i++) {
        if (curTime >= currentLyrics[i].time - 0.25) {
            activeIdx = i;
        } else {
            break;
        }
    }
    if (activeIdx !== -1) {
        document.querySelectorAll(".lyric-line.active").forEach(el => el.classList.remove("active"));
        const activeEl = document.getElementById(`lyric-line-${activeIdx}`);
        if (activeEl && !activeEl.classList.contains("active")) {
            activeEl.classList.add("active");
            activeEl.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }
}

// 10. Night / Sleep Dimmer Screen
document.getElementById("btn-night-mode").addEventListener("click", () => {
    nightDimmer.classList.add("active");
});

nightDimmer.addEventListener("click", () => {
    nightDimmer.classList.remove("active");
});

// Start loop
setInterval(pollState, 700);
pollState();

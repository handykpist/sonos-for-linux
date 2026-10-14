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
let isPolling = false;
async function pollState() {
    if (isPolling) return;
    isPolling = true;
    try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const state = await res.json();
        currentState = state;
        updateUI(state);
    } catch (e) {
        console.warn("Poll state error:", e);
    } finally {
        isPolling = false;
    }
}

function updateUI(state) {
    // Room
    if (state.room) {
        const members = state.group_members || [state.room];
        if (members.length > 1) {
            activeRoomLabel.textContent = `${state.room} + ${members.length - 1}`;
        } else {
            activeRoomLabel.textContent = state.room;
        }
    }

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

// 7. Speaker Grouping & Room Selector Modal
const btnRoomSelect = document.getElementById("btn-room-select");
const btnCloseRoomModal = document.getElementById("btn-close-room-modal");
const btnGroupAll = document.getElementById("btn-group-all");
const btnUngroupAll = document.getElementById("btn-ungroup-all");
let roomVolDebounceTimers = {};

async function loadRoomGroups() {
    if (!roomsList) return;
    roomsList.innerHTML = "<p class='lyrics-notice'>Loading speakers and groups...</p>";
    try {
        const res = await fetch("/api/groups");
        if (!res.ok) throw new Error("Failed to load groups");
        const data = await res.json();
        renderRoomGroups(data);
    } catch (e) {
        console.error("Could not fetch groups:", e);
        roomsList.innerHTML = "<p class='lyrics-notice'>Could not connect to speakers.</p>";
    }
}

function renderRoomGroups(data) {
    roomsList.innerHTML = "";
    const activeRoom = data.active_room || (currentState ? currentState.room : "");
    const rooms = data.rooms || [];

    if (rooms.length === 0) {
        roomsList.innerHTML = "<p class='lyrics-notice'>No Sonos speakers discovered.</p>";
        return;
    }

    rooms.forEach(room => {
        const card = document.createElement("div");
        const isActive = room.is_active || (room.name === activeRoom);
        const isGrouped = room.is_grouped;
        card.className = `room-card ${isActive ? 'is-active' : ''} ${isGrouped ? 'is-grouped' : ''}`;

        // Badge
        let badgeHtml = '';
        if (isActive) {
            badgeHtml = '<span class="room-badge room-badge-master">Host</span>';
        } else if (isGrouped) {
            badgeHtml = '<span class="room-badge room-badge-grouped">Grouped</span>';
        } else {
            badgeHtml = '<span class="room-badge room-badge-solo">Separate</span>';
        }

        // Action Buttons
        let actionButtonsHtml = '';
        if (isActive) {
            actionButtonsHtml = '<span style="font-size:12px; font-weight:700; color:var(--accent); padding:4px 8px;">Active</span>';
        } else {
            const groupBtnClass = isGrouped ? 'btn-group-toggle is-grouped' : 'btn-group-toggle';
            const groupBtnText = isGrouped ? '✓ Grouped' : '+ Group';
            actionButtonsHtml = `
                <button class="${groupBtnClass}" data-room="${room.name}" data-action="toggle-group">${groupBtnText}</button>
                <button class="btn-set-active" data-room="${room.name}" data-action="set-active">Control</button>
            `;
        }

        card.innerHTML = `
            <div class="room-header-row">
                <div class="room-name-wrapper">
                    <span class="room-speaker-icon">${room.muted ? '🔇' : '🔊'}</span>
                    <span class="room-title-text">${room.name}</span>
                    ${badgeHtml}
                </div>
                <div class="room-actions-right">
                    ${actionButtonsHtml}
                </div>
            </div>
            <div class="room-vol-row">
                <button class="btn-room-mute" data-room="${room.name}" title="${room.muted ? 'Unmute' : 'Mute'}">${room.muted ? '🔇' : '🔊'}</button>
                <div class="room-vol-slider-wrap">
                    <button class="btn-room-vol-step btn-vol-minus" data-room="${room.name}">-</button>
                    <input type="range" class="room-vol-range" min="0" max="100" value="${room.volume}" data-room="${room.name}">
                    <button class="btn-room-vol-step btn-vol-plus" data-room="${room.name}">+</button>
                </div>
                <span class="room-vol-val" id="vol-val-${room.name.replace(/\s+/g, '-')}">${room.volume}%</span>
            </div>
        `;

        // Event: Toggle Group
        const toggleBtn = card.querySelector('[data-action="toggle-group"]');
        if (toggleBtn) {
            toggleBtn.addEventListener("click", async () => {
                toggleBtn.disabled = true;
                toggleBtn.textContent = "...";
                if (isGrouped) {
                    await postAction("/api/group/leave", { room: room.name });
                } else {
                    await postAction("/api/group/join", { room: room.name, coordinator: activeRoom });
                }
                setTimeout(loadRoomGroups, 250);
            });
        }

        // Event: Set Active
        const setActiveBtn = card.querySelector('[data-action="set-active"]');
        if (setActiveBtn) {
            setActiveBtn.addEventListener("click", async () => {
                setActiveBtn.disabled = true;
                await postAction("/api/speaker", { room: room.name });
                setTimeout(loadRoomGroups, 200);
            });
        }

        // Event: Mute
        const muteBtn = card.querySelector('.btn-room-mute');
        if (muteBtn) {
            muteBtn.addEventListener("click", async () => {
                await postAction("/api/room/mute", { room: room.name, muted: !room.muted });
                setTimeout(loadRoomGroups, 200);
            });
        }

        // Event: Slider Volume
        const slider = card.querySelector('.room-vol-range');
        const valLabel = card.querySelector('.room-vol-val');
        if (slider && valLabel) {
            slider.addEventListener("input", () => {
                valLabel.textContent = `${slider.value}%`;
                clearTimeout(roomVolDebounceTimers[room.name]);
                roomVolDebounceTimers[room.name] = setTimeout(() => {
                    postAction("/api/room/volume", { room: room.name, volume: parseInt(slider.value, 10) });
                }, 120);
            });
        }

        // Event: Step Minus
        const minusBtn = card.querySelector('.btn-vol-minus');
        if (minusBtn && slider && valLabel) {
            minusBtn.addEventListener("click", () => {
                let v = Math.max(0, parseInt(slider.value, 10) - 3);
                slider.value = v;
                valLabel.textContent = `${v}%`;
                clearTimeout(roomVolDebounceTimers[room.name]);
                roomVolDebounceTimers[room.name] = setTimeout(() => {
                    postAction("/api/room/volume", { room: room.name, volume: v });
                }, 120);
            });
        }

        // Event: Step Plus
        const plusBtn = card.querySelector('.btn-vol-plus');
        if (plusBtn && slider && valLabel) {
            plusBtn.addEventListener("click", () => {
                let v = Math.min(100, parseInt(slider.value, 10) + 3);
                slider.value = v;
                valLabel.textContent = `${v}%`;
                clearTimeout(roomVolDebounceTimers[room.name]);
                roomVolDebounceTimers[room.name] = setTimeout(() => {
                    postAction("/api/room/volume", { room: room.name, volume: v });
                }, 120);
            });
        }

        roomsList.appendChild(card);
    });
}

if (btnRoomSelect) {
    btnRoomSelect.addEventListener("click", () => {
        roomModal.classList.add("open");
        loadRoomGroups();
    });
}

if (btnCloseRoomModal) {
    btnCloseRoomModal.addEventListener("click", () => {
        roomModal.classList.remove("open");
    });
}

if (btnGroupAll) {
    btnGroupAll.addEventListener("click", async () => {
        btnGroupAll.textContent = "Grouping...";
        const activeRoom = currentState ? currentState.room : "";
        await postAction("/api/group/all", { coordinator: activeRoom });
        setTimeout(() => {
            btnGroupAll.textContent = "🔊 Everywhere";
            loadRoomGroups();
        }, 350);
    });
}

if (btnUngroupAll) {
    btnUngroupAll.addEventListener("click", async () => {
        btnUngroupAll.textContent = "Separating...";
        await postAction("/api/group/ungroup_all", {});
        setTimeout(() => {
            btnUngroupAll.textContent = "Separate";
            loadRoomGroups();
        }, 350);
    });
}

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

// 11. Hidden Bottom-Left Corner Power & Exit Button
const btnHiddenPower = document.getElementById("btn-hidden-power");
const powerModal = document.getElementById("power-modal");
const btnClosePowerModal = document.getElementById("btn-close-power-modal");

if (btnHiddenPower) {
    btnHiddenPower.addEventListener("click", () => {
        if (powerModal) powerModal.classList.add("open");
    });
}

if (btnClosePowerModal) {
    btnClosePowerModal.addEventListener("click", () => {
        if (powerModal) powerModal.classList.remove("open");
    });
}

function handleSystemAction(endpoint, confirmMsg, actionIcon, actionTitle, actionSub) {
    if (confirmMsg && !confirm(confirmMsg)) return;

    if (powerModal) {
        powerModal.querySelector(".modal-card").innerHTML = `
            <div style="text-align:center; padding:36px 12px;">
                <div style="font-size:42px; margin-bottom:14px;">${actionIcon || "⏳"}</div>
                <h2 style="font-size:22px; font-weight:700;">${actionTitle || "Executing command..."}</h2>
                <p style="color:rgba(255,255,255,0.6); margin-top:8px; font-size:14px;">${actionSub || "Please wait while the system responds."}</p>
            </div>
        `;
    }

    fetch(endpoint, { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (endpoint === "/api/system/exit") {
                setTimeout(() => {
                    try { window.close(); } catch(e) {}
                }, 400);
            }
        })
        .catch(err => console.error("System action error:", err));
}

document.getElementById("btn-power-exit")?.addEventListener("click", () => {
    handleSystemAction("/api/system/exit", null, "🚪", "Exiting to Desktop...", "Closing kiosk window and stopping controller.");
});

document.getElementById("btn-power-restart")?.addEventListener("click", () => {
    handleSystemAction("/api/system/restart", null, "🔄", "Restarting Sonos App...", "Reloading UI and UPnP services.");
});

document.getElementById("btn-power-reboot")?.addEventListener("click", () => {
    handleSystemAction("/api/system/reboot", "Reboot the Raspberry Pi?", "⚡", "Rebooting Raspberry Pi...", "System is restarting.");
});

document.getElementById("btn-power-shutdown")?.addEventListener("click", () => {
    handleSystemAction("/api/system/shutdown", "Safely shut down the Raspberry Pi?", "🛑", "Shutting Down...", "Safe to unplug power when screen turns off.");
});

// 12. Music Search Drawer & Touch Virtual Keyboard
const searchDrawer = document.getElementById("search-drawer");
const btnSearchToggle = document.getElementById("btn-search-toggle");
const btnCloseSearch = document.getElementById("btn-close-search");
const searchInput = document.getElementById("search-input");
const btnClearSearch = document.getElementById("btn-clear-search");
const btnExecSearch = document.getElementById("btn-exec-search");
const btnToggleKeyboard = document.getElementById("btn-toggle-keyboard");
const virtualKeyboard = document.getElementById("virtual-keyboard");
const searchResultsContent = document.getElementById("search-results-content");
const searchDrilldown = document.getElementById("search-drilldown");
const btnBackDrilldown = document.getElementById("btn-back-drilldown");
const drilldownTitle = document.getElementById("drilldown-title");
const drilldownSubtitle = document.getElementById("drilldown-subtitle");
const btnDrilldownPlayAll = document.getElementById("btn-drilldown-play-all");
const drilldownItems = document.getElementById("drilldown-items");

let currentSearchCategory = "all";
let searchDebounceTimer = null;
let currentDrilldownId = "";
let currentDrilldownTitle = "";

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

if (btnSearchToggle) {
    btnSearchToggle.addEventListener("click", () => {
        searchDrawer.classList.add("open");
    });
}

if (btnCloseSearch) {
    btnCloseSearch.addEventListener("click", () => {
        searchDrawer.classList.remove("open");
    });
}

// Category filter tabs
document.querySelectorAll(".cat-pill").forEach(pill => {
    pill.addEventListener("click", () => {
        document.querySelectorAll(".cat-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        currentSearchCategory = pill.dataset.cat || "all";
        const q = searchInput ? searchInput.value.trim() : "";
        if (q) performSearch(q, currentSearchCategory);
    });
});

// Toggle virtual keyboard
if (btnToggleKeyboard && virtualKeyboard) {
    btnToggleKeyboard.addEventListener("click", () => {
        virtualKeyboard.classList.toggle("collapsed");
    });
}

// Virtual Keyboard input
document.querySelectorAll(".kb-key").forEach(keyBtn => {
    keyBtn.addEventListener("click", (e) => {
        e.preventDefault();
        if (!searchInput) return;
        const key = keyBtn.dataset.key;
        const action = keyBtn.dataset.action;
        if (key) {
            searchInput.value += key;
        } else if (action === "space") {
            searchInput.value += " ";
        } else if (action === "backspace") {
            searchInput.value = searchInput.value.slice(0, -1);
        } else if (action === "search") {
            const q = searchInput.value.trim();
            if (q) performSearch(q, currentSearchCategory);
            return;
        } else if (action === "hide") {
            if (virtualKeyboard) virtualKeyboard.classList.add("collapsed");
            return;
        }
        if (btnClearSearch) btnClearSearch.style.display = searchInput.value.length > 0 ? "flex" : "none";
        triggerDebouncedSearch();
    });
});

function triggerDebouncedSearch() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        const q = searchInput ? searchInput.value.trim() : "";
        if (q.length >= 1) {
            performSearch(q, currentSearchCategory);
        } else {
            resetSearchUI();
        }
    }, 350);
}

if (searchInput) {
    searchInput.addEventListener("input", () => {
        if (btnClearSearch) btnClearSearch.style.display = searchInput.value.length > 0 ? "flex" : "none";
        triggerDebouncedSearch();
    });
    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const q = searchInput.value.trim();
            if (q) performSearch(q, currentSearchCategory);
        }
    });
}

if (btnClearSearch) {
    btnClearSearch.addEventListener("click", () => {
        if (searchInput) searchInput.value = "";
        btnClearSearch.style.display = "none";
        resetSearchUI();
    });
}

if (btnExecSearch) {
    btnExecSearch.addEventListener("click", () => {
        const q = searchInput ? searchInput.value.trim() : "";
        if (q) performSearch(q, currentSearchCategory);
    });
}

function resetSearchUI() {
    if (searchDrilldown) searchDrilldown.style.display = "none";
    if (searchResultsContent) {
        searchResultsContent.style.display = "block";
        searchResultsContent.innerHTML = `
            <div class="search-initial-placeholder">
                <span class="placeholder-icon">🎵</span>
                <p class="placeholder-text">Type an artist, song, or album name to search your Sonos library</p>
            </div>
        `;
    }
}

async function performSearch(query, category) {
    if (!searchResultsContent) return;
    if (searchDrilldown) searchDrilldown.style.display = "none";
    searchResultsContent.style.display = "block";
    searchResultsContent.innerHTML = "<p class='lyrics-notice'>Searching Sonos library...</p>";

    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}`);
        if (!res.ok) throw new Error("Search request failed");
        const data = await res.json();
        renderSearchResults(data, query);
    } catch (e) {
        console.error("Search error:", e);
        searchResultsContent.innerHTML = "<p class='lyrics-notice'>Search error or music library not reachable.</p>";
    }
}

function renderSearchResults(data, query) {
    searchResultsContent.innerHTML = "";
    const artists = data.artists || [];
    const tracks = data.tracks || [];
    const albums = data.albums || [];
    const favorites = data.favorites || [];

    const totalResults = artists.length + tracks.length + albums.length + favorites.length;
    if (totalResults === 0) {
        searchResultsContent.innerHTML = `
            <div class="search-initial-placeholder">
                <span class="placeholder-icon">🔍</span>
                <p class="placeholder-text">No results found for "${escapeHtml(query)}" in your Sonos library.</p>
            </div>
        `;
        return;
    }

    // 1. Artists Section
    if (artists.length > 0) {
        const sec = document.createElement("div");
        sec.className = "search-section";
        sec.innerHTML = `
            <div class="search-section-header">
                <span class="search-section-title">🎤 Artists</span>
                <span class="search-section-count">${artists.length} found</span>
            </div>
            <div class="artist-results-grid" id="grid-artists"></div>
        `;
        const grid = sec.querySelector("#grid-artists");
        artists.forEach(art => {
            const card = document.createElement("div");
            card.className = "artist-card";
            card.innerHTML = `
                <div class="artist-card-icon">🎤</div>
                <div class="artist-card-name">${escapeHtml(art.title)}</div>
                <div class="artist-card-sub">Browse artist</div>
            `;
            card.addEventListener("click", () => {
                openDrilldown(art.id, art.title, `Albums & Tracks by ${art.title}`);
            });
            grid.appendChild(card);
        });
        searchResultsContent.appendChild(sec);
    }

    // 2. Albums Section
    if (albums.length > 0) {
        const sec = document.createElement("div");
        sec.className = "search-section";
        sec.innerHTML = `
            <div class="search-section-header">
                <span class="search-section-title">💿 Albums</span>
                <span class="search-section-count">${albums.length} found</span>
            </div>
            <div class="album-results-grid" id="grid-albums"></div>
        `;
        const grid = sec.querySelector("#grid-albums");
        albums.forEach(alb => {
            const card = document.createElement("div");
            card.className = "album-card";
            card.innerHTML = `
                <img class="album-card-art" src="${alb.art || ''}" onerror="this.style.display='none'">
                <div class="album-card-info">
                    <div class="album-card-title">${escapeHtml(alb.title)}</div>
                    <div class="album-card-artist">${escapeHtml(alb.artist || 'Album')}</div>
                </div>
            `;
            card.addEventListener("click", () => {
                openDrilldown(alb.id, alb.title, alb.artist || "Album Tracks");
            });
            grid.appendChild(card);
        });
        searchResultsContent.appendChild(sec);
    }

    // 3. Tracks / Songs Section
    if (tracks.length > 0) {
        const sec = document.createElement("div");
        sec.className = "search-section";
        sec.innerHTML = `
            <div class="search-section-header">
                <span class="search-section-title">🎵 Songs</span>
                <span class="search-section-count">${tracks.length} found</span>
            </div>
            <div class="track-results-list" id="list-tracks"></div>
        `;
        const list = sec.querySelector("#list-tracks");
        tracks.forEach(trk => {
            const item = document.createElement("div");
            item.className = "track-result-item";
            item.innerHTML = `
                <img class="track-result-art" src="${trk.art || ''}" onerror="this.style.display='none'">
                <div class="track-result-info">
                    <div class="track-result-title">${escapeHtml(trk.title)}</div>
                    <div class="track-result-meta">${escapeHtml(trk.artist || '')} ${trk.album ? '• ' + escapeHtml(trk.album) : ''}</div>
                </div>
                <div class="track-result-actions">
                    <button class="btn-item-play">▶ Play</button>
                    <button class="btn-item-queue">+ Queue</button>
                </div>
            `;
            const playBtn = item.querySelector(".btn-item-play");
            playBtn.addEventListener("click", async () => {
                playBtn.textContent = "Playing...";
                await postAction("/api/play/item", { uri: trk.uri, meta: trk.meta, is_container: false, item_id: trk.id });
                setTimeout(() => { playBtn.textContent = "▶ Play"; }, 1000);
            });

            const queueBtn = item.querySelector(".btn-item-queue");
            queueBtn.addEventListener("click", async () => {
                queueBtn.textContent = "Queued ✓";
                await postAction("/api/queue/item", { uri: trk.uri, meta: trk.meta, is_container: false, item_id: trk.id });
                setTimeout(() => { queueBtn.textContent = "+ Queue"; }, 1200);
            });

            list.appendChild(item);
        });
        searchResultsContent.appendChild(sec);
    }

    // 4. Favorites & Radio Section
    if (favorites.length > 0) {
        const sec = document.createElement("div");
        sec.className = "search-section";
        sec.innerHTML = `
            <div class="search-section-header">
                <span class="search-section-title">⭐ Favorites & Radio</span>
                <span class="search-section-count">${favorites.length} found</span>
            </div>
            <div class="track-results-list" id="list-favs"></div>
        `;
        const list = sec.querySelector("#list-favs");
        favorites.forEach(fav => {
            const item = document.createElement("div");
            item.className = "track-result-item";
            item.innerHTML = `
                <img class="track-result-art" src="${fav.art || ''}" onerror="this.style.display='none'">
                <div class="track-result-info">
                    <div class="track-result-title">${escapeHtml(fav.title)}</div>
                    <div class="track-result-meta">Sonos Favorite</div>
                </div>
                <div class="track-result-actions">
                    <button class="btn-item-play">▶ Play</button>
                </div>
            `;
            const playBtn = item.querySelector(".btn-item-play");
            playBtn.addEventListener("click", async () => {
                playBtn.textContent = "Playing...";
                await postAction("/api/favorite/play", { uri: fav.uri, meta: fav.meta });
                setTimeout(() => { playBtn.textContent = "▶ Play"; }, 1000);
            });
            list.appendChild(item);
        });
        searchResultsContent.appendChild(sec);
    }
}

// Drilldown View (Browsing Artist or Album)
async function openDrilldown(containerId, title, subtitle) {
    if (!searchDrilldown || !searchResultsContent) return;
    currentDrilldownId = containerId;
    currentDrilldownTitle = title;
    if (drilldownTitle) drilldownTitle.textContent = title;
    if (drilldownSubtitle) drilldownSubtitle.textContent = subtitle || "Browsing";
    if (drilldownItems) drilldownItems.innerHTML = "<p class='lyrics-notice'>Loading items...</p>";

    searchResultsContent.style.display = "none";
    searchDrilldown.style.display = "flex";

    try {
        const res = await fetch(`/api/browse?id=${encodeURIComponent(containerId)}`);
        if (!res.ok) throw new Error("Browse failed");
        const data = await res.json();
        renderDrilldownItems(data.items || []);
    } catch (e) {
        console.error("Browse error:", e);
        if (drilldownItems) drilldownItems.innerHTML = "<p class='lyrics-notice'>Could not load items.</p>";
    }
}

function renderDrilldownItems(items) {
    if (!drilldownItems) return;
    drilldownItems.innerHTML = "";
    if (items.length === 0) {
        drilldownItems.innerHTML = "<p class='lyrics-notice'>No items found in this section.</p>";
        return;
    }

    items.forEach(item => {
        if (item.is_container) {
            const el = document.createElement("div");
            el.className = "album-card";
            el.style.width = "100%";
            el.innerHTML = `
                <div class="artist-card-icon" style="width:36px; height:36px; font-size:16px; margin-bottom:0;">📁</div>
                <div class="album-card-info" style="flex:1;">
                    <div class="album-card-title">${escapeHtml(item.title)}</div>
                    <div class="album-card-artist">${escapeHtml(item.artist || 'Album / Collection')}</div>
                </div>
                <span style="font-size:12px; color:var(--accent); font-weight:700;">Open →</span>
            `;
            el.addEventListener("click", () => {
                openDrilldown(item.id, item.title, item.artist || item.title);
            });
            drilldownItems.appendChild(el);
        } else {
            const el = document.createElement("div");
            el.className = "track-result-item";
            el.innerHTML = `
                <img class="track-result-art" src="${item.art || ''}" onerror="this.style.display='none'">
                <div class="track-result-info">
                    <div class="track-result-title">${escapeHtml(item.title)}</div>
                    <div class="track-result-meta">${escapeHtml(item.artist || '')} ${item.album ? '• ' + escapeHtml(item.album) : ''}</div>
                </div>
                <div class="track-result-actions">
                    <button class="btn-item-play">▶ Play</button>
                    <button class="btn-item-queue">+ Queue</button>
                </div>
            `;
            const playBtn = el.querySelector(".btn-item-play");
            playBtn.addEventListener("click", async () => {
                playBtn.textContent = "Playing...";
                await postAction("/api/play/item", { uri: item.uri, meta: item.meta, is_container: false, item_id: item.id });
                setTimeout(() => { playBtn.textContent = "▶ Play"; }, 1000);
            });

            const queueBtn = el.querySelector(".btn-item-queue");
            queueBtn.addEventListener("click", async () => {
                queueBtn.textContent = "Queued ✓";
                await postAction("/api/queue/item", { uri: item.uri, meta: item.meta, is_container: false, item_id: item.id });
                setTimeout(() => { queueBtn.textContent = "+ Queue"; }, 1200);
            });

            drilldownItems.appendChild(el);
        }
    });
}

if (btnBackDrilldown) {
    btnBackDrilldown.addEventListener("click", () => {
        if (searchDrilldown) searchDrilldown.style.display = "none";
        if (searchResultsContent) searchResultsContent.style.display = "block";
    });
}

if (btnDrilldownPlayAll) {
    btnDrilldownPlayAll.addEventListener("click", async () => {
        if (!currentDrilldownId) return;
        btnDrilldownPlayAll.textContent = "Starting...";
        await postAction("/api/play/item", { is_container: true, item_id: currentDrilldownId });
        setTimeout(() => {
            btnDrilldownPlayAll.textContent = "▶ Play All";
        }, 1200);
    });
}

// Start polling loop
setInterval(pollState, 800);
pollState();


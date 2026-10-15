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
const btnRoomsScrollUp = document.getElementById("btn-rooms-scroll-up");
const btnRoomsScrollDown = document.getElementById("btn-rooms-scroll-down");
const roomModalSubtitle = document.getElementById("room-modal-subtitle");

let touchMovedDistance = 0;

async function loadRoomGroups() {
    if (!roomsList) return;
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

    if (roomModalSubtitle) {
        if (activeRoom) {
            roomModalSubtitle.innerHTML = `Coordinator: <span class="host-highlight">${activeRoom}</span> • Tap speaker to add/remove`;
        } else {
            roomModalSubtitle.textContent = "Tap a speaker to toggle playback in that room";
        }
    }

    if (rooms.length === 0) {
        roomsList.innerHTML = "<p class='lyrics-notice'>Searching for Sonos speakers on local network...</p>";
        return;
    }

    rooms.forEach(room => {
        const card = document.createElement("div");
        const isHost = (room.name === activeRoom);
        const isGrouped = room.is_grouped;

        let cardClass = "room-card";
        let icon = "🔈";
        let statusText = "Standalone / Off";
        let pillHtml = "";

        if (isHost) {
            cardClass += " is-host";
            icon = "🔊";
            statusText = "Host (Playing Here)";
            pillHtml = `<span class="room-toggle-pill pill-host">👑 Host</span>`;
        } else if (isGrouped) {
            cardClass += " is-grouped";
            icon = "🔊";
            statusText = "Playing in sync";
            pillHtml = `<span class="room-toggle-pill pill-playing">✓ Playing</span>`;
        } else {
            cardClass += " is-separate";
            icon = "🔈";
            statusText = "Tap to add to music";
            pillHtml = `<span class="room-toggle-pill pill-add">+ Add</span>`;
        }

        card.className = cardClass;
        card.innerHTML = `
            <div class="room-card-info">
                <div class="room-name-line">
                    <span class="room-spk-icon">${icon}</span>
                    <span class="room-title-text">${room.name}</span>
                </div>
                <span class="room-status-text">${statusText}</span>
            </div>
            <div class="room-card-actions">
                ${pillHtml}
            </div>
        `;

        // Tap on card: toggle grouping (ignore if scrolling)
        card.addEventListener("click", async () => {
            if (touchMovedDistance > 10) {
                return;
            }
            if (isHost) {
                return;
            }

            // Optimistic UI update for instant touch response
            const pill = card.querySelector(".room-toggle-pill");
            const statusLabel = card.querySelector(".room-status-text");
            if (isGrouped) {
                card.className = "room-card is-separate";
                if (pill) {
                    pill.className = "room-toggle-pill pill-add";
                    pill.textContent = "⏳ Leaving...";
                }
                if (statusLabel) statusLabel.textContent = "Separating...";
                await postAction("/api/group/leave", { room: room.name });
            } else {
                card.className = "room-card is-grouped";
                if (pill) {
                    pill.className = "room-toggle-pill pill-playing";
                    pill.textContent = "⏳ Adding...";
                }
                if (statusLabel) statusLabel.textContent = "Joining sync...";
                await postAction("/api/group/join", { room: room.name, coordinator: activeRoom });
            }

            setTimeout(loadRoomGroups, 400);
        });

        roomsList.appendChild(card);
    });
}

// 1-Tap Touch Scroll Arrows
if (btnRoomsScrollUp && roomsList) {
    btnRoomsScrollUp.addEventListener("click", () => {
        roomsList.scrollBy({ top: -140, behavior: "smooth" });
    });
}
if (btnRoomsScrollDown && roomsList) {
    btnRoomsScrollDown.addEventListener("click", () => {
        roomsList.scrollBy({ top: 140, behavior: "smooth" });
    });
}

// Touch & Pointer Drag-to-Scroll for Touchscreens and Kiosks
if (roomsList) {
    let touchStartY = 0;
    let touchStartScroll = 0;
    let isTouchDragging = false;

    roomsList.addEventListener("touchstart", (e) => {
        if (!e.touches || e.touches.length === 0) return;
        touchStartY = e.touches[0].clientY;
        touchStartScroll = roomsList.scrollTop;
        isTouchDragging = true;
        touchMovedDistance = 0;
    }, { passive: true });

    roomsList.addEventListener("touchmove", (e) => {
        if (!isTouchDragging || !e.touches || e.touches.length === 0) return;
        const delta = e.touches[0].clientY - touchStartY;
        touchMovedDistance = Math.abs(delta);
        roomsList.scrollTop = touchStartScroll - delta;
    }, { passive: true });

    roomsList.addEventListener("touchend", () => {
        isTouchDragging = false;
        setTimeout(() => { touchMovedDistance = 0; }, 120);
    });

    roomsList.addEventListener("touchcancel", () => {
        isTouchDragging = false;
        touchMovedDistance = 0;
    });

    // Pointer / mouse drag support (for X11 pointer emulation or desktop browser)
    let isMouseDown = false;
    let mouseStartY = 0;
    let mouseStartScroll = 0;

    roomsList.addEventListener("mousedown", (e) => {
        isMouseDown = true;
        mouseStartY = e.clientY;
        mouseStartScroll = roomsList.scrollTop;
        touchMovedDistance = 0;
    });

    window.addEventListener("mousemove", (e) => {
        if (!isMouseDown) return;
        const delta = e.clientY - mouseStartY;
        touchMovedDistance = Math.abs(delta);
        if (touchMovedDistance > 4) {
            roomsList.scrollTop = mouseStartScroll - delta;
        }
    });

    window.addEventListener("mouseup", () => {
        if (isMouseDown) {
            isMouseDown = false;
            setTimeout(() => { touchMovedDistance = 0; }, 120);
        }
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
        btnGroupAll.disabled = true;
        btnGroupAll.textContent = "Grouping...";
        const activeRoom = currentState ? currentState.room : "";
        // Optimistic UI update across all cards
        document.querySelectorAll(".room-card:not(.is-host)").forEach(card => {
            card.className = "room-card is-grouped";
            const pill = card.querySelector(".room-toggle-pill");
            if (pill) {
                pill.className = "room-toggle-pill pill-playing";
                pill.textContent = "✓ Playing";
            }
            const status = card.querySelector(".room-status-text");
            if (status) status.textContent = "Playing in sync";
        });
        await postAction("/api/group/all", { coordinator: activeRoom });
        setTimeout(() => {
            btnGroupAll.disabled = false;
            btnGroupAll.textContent = "🔊 Group All";
            loadRoomGroups();
        }, 500);
    });
}

if (btnUngroupAll) {
    btnUngroupAll.addEventListener("click", async () => {
        btnUngroupAll.disabled = true;
        btnUngroupAll.textContent = "Separating...";
        // Optimistic UI update across all cards
        document.querySelectorAll(".room-card:not(.is-host)").forEach(card => {
            card.className = "room-card is-separate";
            const pill = card.querySelector(".room-toggle-pill");
            if (pill) {
                pill.className = "room-toggle-pill pill-add";
                pill.textContent = "+ Add";
            }
            const status = card.querySelector(".room-status-text");
            if (status) status.textContent = "Standalone / Off";
        });
        await postAction("/api/group/ungroup_all", {});
        setTimeout(() => {
            btnUngroupAll.disabled = false;
            btnUngroupAll.textContent = "Separate All";
            loadRoomGroups();
        }, 500);
    });
}

// Hash routing for modal direct view
function checkModalHash() {
    if (window.location.hash === "#rooms") {
        roomModal.classList.add("open");
        loadRoomGroups();
    }
}
window.addEventListener("hashchange", checkModalHash);
setTimeout(checkModalHash, 200);

// 8. Sonos Radio, Favorites & Playlists Carousel Drawer
const btnFavoritesToggle = document.getElementById("btn-favorites-toggle");
const btnCloseFavorites = document.getElementById("btn-close-favorites");
const favoritesCarouselTrack = document.getElementById("favorites-carousel-track");
const btnFavPrev = document.getElementById("btn-fav-prev");
const btnFavNext = document.getElementById("btn-fav-next");
const btnFavPagePrev = document.getElementById("btn-fav-page-prev");
const btnFavPageNext = document.getElementById("btn-fav-page-next");
const favPageDots = document.getElementById("fav-page-dots");
const favPageIndicator = document.getElementById("fav-page-indicator");
const btnFavAddCurrent = document.getElementById("btn-fav-add-current");
const btnFavAddCustom = document.getElementById("btn-fav-add-custom");

// Add Favorite Modal elements
const addFavoriteModal = document.getElementById("add-favorite-modal");
const btnCloseAddFav = document.getElementById("btn-close-add-fav");
const btnCancelAddFav = document.getElementById("btn-cancel-add-fav");
const btnSubmitAddFav = document.getElementById("btn-submit-add-fav");
const inputFavTitle = document.getElementById("input-fav-title");
const inputFavUri = document.getElementById("input-fav-uri");

let allFavorites = [];
let currentFavFilter = "all";
let currentFavPage = 0;
let totalFavPages = 1;
const FAVS_PER_PAGE = 6; // 3 columns x 2 rows = 6 items per page (tailored for 800x480)

async function loadFavorites() {
    if (!favoritesCarouselTrack) return;
    favoritesCarouselTrack.innerHTML = `
        <div class="search-initial-placeholder" style="width:100%;">
            <span class="placeholder-icon">⭐</span>
            <p class="placeholder-text">Loading your Sonos favorites and playlists...</p>
        </div>
    `;
    try {
        const res = await fetch("/api/favorites");
        if (!res.ok) throw new Error("Failed to fetch favorites");
        const data = await res.json();
        allFavorites = data.favorites || [];
        currentFavPage = 0;
        renderFavoritesCarousel();
    } catch (e) {
        console.error("Error loading favorites:", e);
        favoritesCarouselTrack.innerHTML = `
            <div class="search-initial-placeholder" style="width:100%;">
                <span class="placeholder-icon">⚠️</span>
                <p class="placeholder-text">Could not load Sonos favorites. Check network connection.</p>
            </div>
        `;
    }
}

function getFilteredFavorites() {
    if (currentFavFilter === "all") return allFavorites;
    if (currentFavFilter === "radio") {
        return allFavorites.filter(f => f.type === "radio");
    }
    if (currentFavFilter === "playlist") {
        return allFavorites.filter(f => f.type === "playlist");
    }
    if (currentFavFilter === "favorite") {
        return allFavorites.filter(f => f.type === "favorite");
    }
    return allFavorites;
}

function renderFavoritesCarousel() {
    if (!favoritesCarouselTrack) return;
    const items = getFilteredFavorites();
    totalFavPages = Math.max(1, Math.ceil(items.length / FAVS_PER_PAGE));
    currentFavPage = Math.min(currentFavPage, totalFavPages - 1);
    currentFavPage = Math.max(0, currentFavPage);

    favoritesCarouselTrack.innerHTML = "";

    if (items.length === 0) {
        favoritesCarouselTrack.innerHTML = `
            <div class="search-initial-placeholder" style="width:100%;">
                <span class="placeholder-icon">⭐</span>
                <p class="placeholder-text">No favorites found in this category. Tap "⭐ + Current" to save what's playing!</p>
            </div>
        `;
        updateFavPaginationUI(0, 1);
        return;
    }

    // Build pages
    for (let p = 0; p < totalFavPages; p++) {
        const pageEl = document.createElement("div");
        pageEl.className = "favorites-page";
        pageEl.id = `fav-page-${p}`;

        const pageItems = items.slice(p * FAVS_PER_PAGE, (p + 1) * FAVS_PER_PAGE);
        pageItems.forEach(fav => {
            const card = document.createElement("div");
            card.className = "favorite-card";

            let iconFallback = "⭐";
            let typeLabel = "Sonos Favorite";
            if (fav.type === "radio") {
                iconFallback = "📻";
                typeLabel = "Radio Station";
            } else if (fav.type === "playlist") {
                iconFallback = "🎵";
                typeLabel = "Playlist";
            }

            const artHtml = fav.art
                ? `<img class="fav-art" src="${escapeHtml(fav.art)}" onerror="this.outerHTML='<div class=\\'fav-icon-fallback\\'>${iconFallback}</div>'">`
                : `<div class="fav-icon-fallback">${iconFallback}</div>`;

            const deleteBtnHtml = fav.can_delete
                ? `<button class="btn-fav-delete" title="Delete Favorite" data-id="${escapeHtml(fav.id)}">✕</button>`
                : ``;

            card.innerHTML = `
                ${artHtml}
                <div class="fav-info">
                    <div class="fav-title" title="${escapeHtml(fav.title)}">${escapeHtml(fav.title)}</div>
                    <span class="fav-type-badge">${iconFallback} ${typeLabel}</span>
                </div>
                ${deleteBtnHtml}
            `;

            // Play on card tap (unless delete button was tapped)
            card.addEventListener("click", async (e) => {
                if (e.target.closest(".btn-fav-delete")) return;
                card.style.transform = "scale(0.95)";
                await postAction("/api/favorite/play", {
                    uri: fav.uri,
                    meta: fav.meta,
                    is_container: fav.is_container,
                    id: fav.id
                });
                setTimeout(() => {
                    card.style.transform = "";
                    favoritesDrawer.classList.remove("open");
                }, 300);
            });

            // Delete favorite
            const deleteBtn = card.querySelector(".btn-fav-delete");
            if (deleteBtn) {
                deleteBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    if (confirm(`Remove "${fav.title}" from Sonos Favorites?`)) {
                        deleteBtn.disabled = true;
                        deleteBtn.textContent = "...";
                        await postAction("/api/favorites/delete", { id: fav.id });
                        await loadFavorites();
                    }
                });
            }

            pageEl.appendChild(card);
        });

        favoritesCarouselTrack.appendChild(pageEl);
    }

    updateFavPaginationUI(currentFavPage, totalFavPages);
    scrollToFavPage(currentFavPage, false);
}

function updateFavPaginationUI(page, total) {
    if (favPageIndicator) {
        favPageIndicator.textContent = `Page ${page + 1} / ${total}`;
    }
    if (btnFavPrev) btnFavPrev.disabled = (page <= 0);
    if (btnFavNext) btnFavNext.disabled = (page >= total - 1);
    if (btnFavPagePrev) btnFavPagePrev.disabled = (page <= 0);
    if (btnFavPageNext) btnFavPageNext.disabled = (page >= total - 1);

    if (favPageDots) {
        favPageDots.innerHTML = "";
        for (let i = 0; i < total; i++) {
            const dot = document.createElement("div");
            dot.className = `fav-dot ${i === page ? 'active' : ''}`;
            dot.addEventListener("click", () => goToFavPage(i));
            favPageDots.appendChild(dot);
        }
    }
}

function scrollToFavPage(pageIndex, smooth = true) {
    if (!favoritesCarouselTrack) return;
    const pageEl = document.getElementById(`fav-page-${pageIndex}`);
    if (pageEl) {
        pageEl.scrollIntoView({ behavior: smooth ? "smooth" : "auto", inline: "start", block: "nearest" });
    } else {
        const targetX = pageIndex * favoritesCarouselTrack.clientWidth;
        favoritesCarouselTrack.scrollTo({ left: targetX, behavior: smooth ? "smooth" : "auto" });
    }
}

function goToFavPage(pageIndex) {
    if (pageIndex < 0 || pageIndex >= totalFavPages) return;
    currentFavPage = pageIndex;
    updateFavPaginationUI(currentFavPage, totalFavPages);
    scrollToFavPage(currentFavPage, true);
}

// Touch Swiping Gestures on Track
let favTouchStartX = 0;
let favTouchStartY = 0;
let isFavSwiping = false;

if (favoritesCarouselTrack) {
    favoritesCarouselTrack.addEventListener("touchstart", (e) => {
        if (!e.touches || e.touches.length === 0) return;
        favTouchStartX = e.touches[0].clientX;
        favTouchStartY = e.touches[0].clientY;
        isFavSwiping = true;
    }, { passive: true });

    favoritesCarouselTrack.addEventListener("touchend", (e) => {
        if (!isFavSwiping || !e.changedTouches || e.changedTouches.length === 0) return;
        isFavSwiping = false;
        const diffX = e.changedTouches[0].clientX - favTouchStartX;
        const diffY = e.changedTouches[0].clientY - favTouchStartY;
        // Detect horizontal swipe
        if (Math.abs(diffX) > 40 && Math.abs(diffX) > Math.abs(diffY)) {
            if (diffX < 0) {
                // Swiped left -> next page
                goToFavPage(currentFavPage + 1);
            } else {
                // Swiped right -> prev page
                goToFavPage(currentFavPage - 1);
            }
        }
    }, { passive: true });

    // Track native scroll to update active dot
    let favScrollDebounce = null;
    favoritesCarouselTrack.addEventListener("scroll", () => {
        clearTimeout(favScrollDebounce);
        favScrollDebounce = setTimeout(() => {
            const width = favoritesCarouselTrack.clientWidth;
            if (width > 0) {
                const detectedPage = Math.round(favoritesCarouselTrack.scrollLeft / width);
                if (detectedPage !== currentFavPage && detectedPage >= 0 && detectedPage < totalFavPages) {
                    currentFavPage = detectedPage;
                    updateFavPaginationUI(currentFavPage, totalFavPages);
                }
            }
        }, 80);
    }, { passive: true });
}

// Arrow and page buttons
if (btnFavPrev) btnFavPrev.addEventListener("click", () => goToFavPage(currentFavPage - 1));
if (btnFavNext) btnFavNext.addEventListener("click", () => goToFavPage(currentFavPage + 1));
if (btnFavPagePrev) btnFavPagePrev.addEventListener("click", () => goToFavPage(currentFavPage - 1));
if (btnFavPageNext) btnFavPageNext.addEventListener("click", () => goToFavPage(currentFavPage + 1));

// Filter tab clicks
document.querySelectorAll(".fav-tab-pill").forEach(pill => {
    pill.addEventListener("click", () => {
        document.querySelectorAll(".fav-tab-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        currentFavFilter = pill.dataset.tab || "all";
        currentFavPage = 0;
        renderFavoritesCarousel();
    });
});

// Open / Close favorites drawer
if (btnFavoritesToggle) {
    btnFavoritesToggle.addEventListener("click", () => {
        favoritesDrawer.classList.add("open");
        loadFavorites();
    });
}

if (btnCloseFavorites) {
    btnCloseFavorites.addEventListener("click", () => {
        favoritesDrawer.classList.remove("open");
    });
}

// Add Current Track/Station to Favorites
if (btnFavAddCurrent) {
    btnFavAddCurrent.addEventListener("click", async () => {
        btnFavAddCurrent.textContent = "⭐ Saving...";
        try {
            const res = await fetch("/api/favorites/add_current", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                btnFavAddCurrent.textContent = "Saved ⭐";
                await loadFavorites();
                goToFavPage(totalFavPages - 1);
            } else {
                alert(data.error || "Could not save to favorites.");
                btnFavAddCurrent.textContent = "⭐ + Current";
            }
        } catch (e) {
            btnFavAddCurrent.textContent = "⭐ + Current";
        }
        setTimeout(() => {
            btnFavAddCurrent.textContent = "⭐ + Current";
        }, 1500);
    });
}

// Add Custom Radio Station Modal
if (btnFavAddCustom) {
    btnFavAddCustom.addEventListener("click", () => {
        if (addFavoriteModal) {
            if (inputFavTitle) inputFavTitle.value = "";
            if (inputFavUri) inputFavUri.value = "";
            addFavoriteModal.classList.add("open");
        }
    });
}

if (btnCloseAddFav) {
    btnCloseAddFav.addEventListener("click", () => {
        if (addFavoriteModal) addFavoriteModal.classList.remove("open");
    });
}

if (btnCancelAddFav) {
    btnCancelAddFav.addEventListener("click", () => {
        if (addFavoriteModal) addFavoriteModal.classList.remove("open");
    });
}

if (btnSubmitAddFav) {
    btnSubmitAddFav.addEventListener("click", async () => {
        const title = inputFavTitle ? inputFavTitle.value.trim() : "";
        const uri = inputFavUri ? inputFavUri.value.trim() : "";
        if (!title || !uri) {
            alert("Please enter both a station name and a stream URL.");
            return;
        }
        btnSubmitAddFav.textContent = "Saving...";
        btnSubmitAddFav.disabled = true;
        try {
            const res = await fetch("/api/favorites/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, uri })
            });
            const data = await res.json();
            if (data.success) {
                if (addFavoriteModal) addFavoriteModal.classList.remove("open");
                await loadFavorites();
                goToFavPage(totalFavPages - 1);
            } else {
                alert("Failed to save to Sonos Favorites.");
            }
        } catch (e) {
            alert("Error saving favorite.");
        } finally {
            btnSubmitAddFav.textContent = "Save to Sonos Favorites";
            btnSubmitAddFav.disabled = false;
        }
    });
}

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

document.getElementById("btn-power-update")?.addEventListener("click", () => {
    handleSystemAction("/api/update/trigger", "Check for and apply updates from your Git repository now?", "📥", "Updating Sonos Touchscreen...", "Checking remote Git repository, pulling updates, and restarting the controller.");
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
                    <button class="btn-item-fav" title="Save to Favorites">⭐ Fav</button>
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

            const favBtn = item.querySelector(".btn-item-fav");
            favBtn?.addEventListener("click", async () => {
                favBtn.textContent = "Saving...";
                await postAction("/api/favorites/add", {
                    title: trk.title + (trk.artist ? ` – ${trk.artist}` : ""),
                    uri: trk.uri,
                    meta: trk.meta,
                    art: trk.art
                });
                favBtn.textContent = "Saved ⭐";
                setTimeout(() => { favBtn.textContent = "⭐ Fav"; }, 1200);
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
                    <button class="btn-item-fav" title="Save to Favorites">⭐ Fav</button>
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

            const favBtn = el.querySelector(".btn-item-fav");
            favBtn?.addEventListener("click", async () => {
                favBtn.textContent = "Saving...";
                await postAction("/api/favorites/add", {
                    title: item.title + (item.artist ? ` – ${item.artist}` : ""),
                    uri: item.uri,
                    meta: item.meta,
                    art: item.art
                });
                favBtn.textContent = "Saved ⭐";
                setTimeout(() => { favBtn.textContent = "⭐ Fav"; }, 1200);
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


#!/usr/bin/env python3
"""
Sonos S1 Controller - Native Linux Desktop Application
Provides full playback control, volume, room switching, and music browsing (Favorites, Radio, Playlists, Queue).
"""

import os
import sys
import time
import threading
import urllib.request
from typing import Optional, Dict, List, Any

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from sonos_backend import SonosManager, SonosSpeaker

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PROJECT_DIR, "sonos.png")

CSS_DATA = b"""
window {
    background-color: #1e1e24;
    color: #e6e6e6;
}
.header-bar {
    background: #18181c;
    border-bottom: 1px solid #2d2d35;
}
.sidebar {
    background-color: #18181c;
    border-right: 1px solid #2d2d35;
}
.section-title {
    font-size: 11px;
    font-weight: bold;
    color: #7b7b88;
    letter-spacing: 1px;
}
.nav-button {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    margin: 1px 8px;
    font-size: 13px;
    font-weight: 500;
    color: #b0b0b8;
}
.nav-button:hover {
    background: #282832;
    color: #ffffff;
}
.nav-button-active {
    background: #3b3b4a;
    color: #ffffff;
    font-weight: bold;
}
.room-button {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 9px 12px;
    margin: 1px 8px;
    font-size: 13px;
    font-weight: 500;
    color: #c0c0c8;
}
.room-button:hover {
    background: #282832;
    color: #ffffff;
}
.room-button-active {
    background: #2b3a4a;
    color: #58a6ff;
    font-weight: bold;
}
.now-playing-title {
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
}
.now-playing-artist {
    font-size: 16px;
    color: #a0a0ab;
}
.now-playing-album {
    font-size: 14px;
    color: #7b7b88;
}
.play-button {
    background: #ffffff;
    color: #121212;
    border-radius: 26px;
    min-width: 52px;
    min-height: 52px;
    font-size: 20px;
    font-weight: bold;
}
.play-button:hover {
    background: #e0e0e0;
}
.control-button {
    background: transparent;
    color: #d0d0d8;
    border: none;
    border-radius: 20px;
    min-width: 40px;
    min-height: 40px;
    font-size: 16px;
}
.control-button:hover {
    background: #2a2a34;
    color: #ffffff;
}
.art-frame {
    border-radius: 12px;
    background: #121215;
}
.item-row {
    background: #22222a;
    border: 1px solid #2d2d38;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 3px 6px;
}
.item-row:hover {
    background: #2b2b35;
    border-color: #3f3f50;
}
.item-title {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
}
.item-desc {
    font-size: 12px;
    color: #8b8b98;
}
.btn-play-item {
    background: #2d2d38;
    color: #ffffff;
    border-radius: 16px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: bold;
}
.btn-play-item:hover {
    background: #3f3f52;
}
.search-entry {
    background: #18181c;
    color: #ffffff;
    border: 1px solid #33333e;
    border-radius: 8px;
    padding: 6px 10px;
}
"""

class SonosApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sonos S1 Controller")
        self.set_default_size(980, 620)
        self.set_position(Gtk.WindowPosition.CENTER)

        if os.path.exists(ICON_PATH):
            try:
                self.set_icon_from_file(ICON_PATH)
            except Exception:
                pass

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS_DATA)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.manager = SonosManager()
        self.current_art_url = ""
        self.is_slider_dragging = False
        self.running = True

        # Cache for browse items
        self.favorites_data: List[Dict[str, Any]] = []
        self.radio_data: List[Dict[str, Any]] = []
        self.playlist_data: List[Dict[str, Any]] = []
        self.queue_data: List[Dict[str, Any]] = []

        self.build_ui()
        self.connect("destroy", self.on_destroy)

        # Start initial discovery
        threading.Thread(target=self.initial_discovery, daemon=True).start()

    def build_ui(self):
        # HeaderBar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Sonos S1 Controller")
        header.set_subtitle("Linux Desktop")
        header.get_style_context().add_class("header-bar")
        self.set_titlebar(header)

        # Top Refresh Button
        refresh_btn = Gtk.Button()
        refresh_btn.set_tooltip_text("Refresh Sonos Network & Content")
        icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_btn.set_image(icon)
        refresh_btn.connect("clicked", lambda b: threading.Thread(target=self.refresh_all, daemon=True).start())
        header.pack_end(refresh_btn)

        # Main Layout: Sidebar (Rooms & Navigation) + Content Stack + Bottom Player Bar
        root_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root_vbox)

        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root_vbox.pack_start(main_hbox, True, True, 0)

        # ----------------- SIDEBAR -----------------
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_size_request(230, -1)
        sidebar.get_style_context().add_class("sidebar")
        main_hbox.pack_start(sidebar, False, False, 0)

        # Rooms Header
        rooms_title = Gtk.Label(label="ROOMS & GROUPS")
        rooms_title.set_halign(Gtk.Align.START)
        rooms_title.set_margin_start(16)
        rooms_title.set_margin_top(16)
        rooms_title.set_margin_bottom(6)
        rooms_title.get_style_context().add_class("section-title")
        sidebar.pack_start(rooms_title, False, False, 0)

        # Rooms List
        self.rooms_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scrolled_rooms = Gtk.ScrolledWindow()
        scrolled_rooms.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_rooms.set_size_request(-1, 140)
        scrolled_rooms.add(self.rooms_box)
        sidebar.pack_start(scrolled_rooms, False, False, 0)

        # Browse Navigation Header
        nav_title = Gtk.Label(label="MUSIC & SOURCES")
        nav_title.set_halign(Gtk.Align.START)
        nav_title.set_margin_start(16)
        nav_title.set_margin_top(14)
        nav_title.set_margin_bottom(6)
        nav_title.get_style_context().add_class("section-title")
        sidebar.pack_start(nav_title, False, False, 0)

        # Navigation Buttons (Now Playing, Favorites, Radio, Playlists, Queue)
        self.nav_buttons = {}
        nav_items = [
            ("now_playing", "🎵  Now Playing"),
            ("favorites", "⭐  Sonos Favorites"),
            ("radio", "📻  Radio Stations"),
            ("playlists", "📜  Sonos Playlists"),
            ("queue", "📋  Current Queue")
        ]

        for view_id, label_text in nav_items:
            btn = Gtk.Button(label=label_text)
            if btn.get_child():
                btn.get_child().set_halign(Gtk.Align.START)
            btn.get_style_context().add_class("nav-button")
            btn.connect("clicked", self.make_nav_handler(view_id))
            sidebar.pack_start(btn, False, False, 0)
            self.nav_buttons[view_id] = btn

        # ----------------- MAIN CONTENT STACK -----------------
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        main_hbox.pack_start(self.stack, True, True, 0)

        # View 1: Now Playing
        self.view_now_playing = self.create_now_playing_view()
        self.stack.add_named(self.view_now_playing, "now_playing")

        # View 2: Sonos Favorites
        self.view_favorites = self.create_favorites_view()
        self.stack.add_named(self.view_favorites, "favorites")

        # View 3: Radio Stations
        self.view_radio = self.create_radio_view()
        self.stack.add_named(self.view_radio, "radio")

        # View 4: Playlists
        self.view_playlists = self.create_playlists_view()
        self.stack.add_named(self.view_playlists, "playlists")

        # View 5: Queue
        self.view_queue = self.create_queue_view()
        self.stack.add_named(self.view_queue, "queue")

        # Set initial active nav
        self.set_active_nav("now_playing")

        # ----------------- BOTTOM PLAYER BAR -----------------
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        bottom_bar.get_style_context().add_class("header-bar")
        bottom_bar.set_size_request(-1, 72)
        bottom_bar.set_margin_start(16)
        bottom_bar.set_margin_end(16)
        root_vbox.pack_end(bottom_bar, False, False, 0)

        # Mini Track Info on the Left
        mini_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        mini_info_box.set_valign(Gtk.Align.CENTER)
        mini_info_box.set_size_request(220, -1)
        bottom_bar.pack_start(mini_info_box, False, False, 0)

        self.lbl_mini_title = Gtk.Label(label="No music playing")
        self.lbl_mini_title.set_halign(Gtk.Align.START)
        self.lbl_mini_title.set_ellipsize(3) # PANGO_ELLIPSIZE_END
        self.lbl_mini_title.get_style_context().add_class("item-title")
        mini_info_box.pack_start(self.lbl_mini_title, False, False, 0)

        self.lbl_mini_artist = Gtk.Label(label="")
        self.lbl_mini_artist.set_halign(Gtk.Align.START)
        self.lbl_mini_artist.set_ellipsize(3)
        self.lbl_mini_artist.get_style_context().add_class("item-desc")
        mini_info_box.pack_start(self.lbl_mini_artist, False, False, 0)

        # Center Transport Buttons (Prev, Play/Pause, Next)
        transport_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        transport_box.set_valign(Gtk.Align.CENTER)
        bottom_bar.pack_start(transport_box, True, False, 0)

        self.btn_prev = Gtk.Button(label="⏮")
        self.btn_prev.get_style_context().add_class("control-button")
        self.btn_prev.connect("clicked", lambda b: self.run_async(lambda: self.manager.active_speaker and self.manager.active_speaker.previous_track()))
        transport_box.pack_start(self.btn_prev, False, False, 0)

        self.btn_play = Gtk.Button(label="▶")
        self.btn_play.get_style_context().add_class("play-button")
        self.btn_play.connect("clicked", self.on_toggle_play)
        transport_box.pack_start(self.btn_play, False, False, 0)

        self.btn_next = Gtk.Button(label="⏭")
        self.btn_next.get_style_context().add_class("control-button")
        self.btn_next.connect("clicked", lambda b: self.run_async(lambda: self.manager.active_speaker and self.manager.active_speaker.next_track()))
        transport_box.pack_start(self.btn_next, False, False, 0)

        # Volume Controls on the Right
        volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        volume_box.set_valign(Gtk.Align.CENTER)
        volume_box.set_size_request(240, -1)
        bottom_bar.pack_end(volume_box, False, False, 0)

        self.btn_mute = Gtk.Button(label="🔊")
        self.btn_mute.get_style_context().add_class("control-button")
        self.btn_mute.connect("clicked", self.on_toggle_mute)
        volume_box.pack_start(self.btn_mute, False, False, 0)

        self.volume_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume_slider.set_draw_value(False)
        self.volume_slider.connect("value-changed", self.on_volume_changed)
        volume_box.pack_start(self.volume_slider, True, True, 0)

        self.lbl_volume = Gtk.Label(label="50%")
        self.lbl_volume.set_size_request(42, -1)
        volume_box.pack_start(self.lbl_volume, False, False, 0)

    # ----------------- VIEW BUILDERS -----------------

    def create_now_playing_view(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_margin_top(28)
        vbox.set_margin_bottom(28)
        vbox.set_margin_start(36)
        vbox.set_margin_end(36)

        card_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=28)
        vbox.pack_start(card_box, True, True, 0)

        # Album Art
        self.art_image = Gtk.Image()
        self.art_image.set_size_request(240, 240)
        self.art_image.get_style_context().add_class("art-frame")
        self.set_default_album_art()
        card_box.pack_start(self.art_image, False, False, 0)

        # Track Details & Progress
        meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        meta_box.set_valign(Gtk.Align.CENTER)
        card_box.pack_start(meta_box, True, True, 0)

        self.lbl_room_indicator = Gtk.Label(label="Connecting...")
        self.lbl_room_indicator.set_halign(Gtk.Align.START)
        self.lbl_room_indicator.get_style_context().add_class("section-title")
        meta_box.pack_start(self.lbl_room_indicator, False, False, 0)

        self.lbl_title = Gtk.Label(label="No music playing")
        self.lbl_title.set_halign(Gtk.Align.START)
        self.lbl_title.set_line_wrap(True)
        self.lbl_title.get_style_context().add_class("now-playing-title")
        meta_box.pack_start(self.lbl_title, False, False, 0)

        self.lbl_artist = Gtk.Label(label="")
        self.lbl_artist.set_halign(Gtk.Align.START)
        self.lbl_artist.get_style_context().add_class("now-playing-artist")
        meta_box.pack_start(self.lbl_artist, False, False, 0)

        self.lbl_album = Gtk.Label(label="")
        self.lbl_album.set_halign(Gtk.Align.START)
        self.lbl_album.get_style_context().add_class("now-playing-album")
        meta_box.pack_start(self.lbl_album, False, False, 0)

        # Progress / Seeker Bar
        progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        meta_box.pack_start(progress_box, False, False, 12)

        self.lbl_rel_time = Gtk.Label(label="0:00")
        self.lbl_rel_time.get_style_context().add_class("item-desc")
        progress_box.pack_start(self.lbl_rel_time, False, False, 0)

        self.seek_bar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.seek_bar.set_draw_value(False)
        self.seek_bar.connect("button-press-event", self.on_seek_press)
        self.seek_bar.connect("button-release-event", self.on_seek_release)
        progress_box.pack_start(self.seek_bar, True, True, 0)

        self.lbl_duration = Gtk.Label(label="0:00")
        self.lbl_duration.get_style_context().add_class("item-desc")
        progress_box.pack_start(self.lbl_duration, False, False, 0)

        return vbox

    def create_favorites_view(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)

        # Filter Entry
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.fav_search = Gtk.SearchEntry()
        self.fav_search.set_placeholder_text("Search Sonos favorites...")
        self.fav_search.get_style_context().add_class("search-entry")
        self.fav_search.connect("search-changed", self.on_fav_search_changed)
        filter_box.pack_start(self.fav_search, True, True, 0)
        vbox.pack_start(filter_box, False, False, 0)

        # Scrolled List
        self.favorites_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.favorites_list_box)
        vbox.pack_start(scrolled, True, True, 0)

        return vbox

    def create_radio_view(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)

        title = Gtk.Label(label="RADIO STATIONS & STREAMS")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("section-title")
        vbox.pack_start(title, False, False, 0)

        self.radio_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.radio_list_box)
        vbox.pack_start(scrolled, True, True, 0)

        return vbox

    def create_playlists_view(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)

        title = Gtk.Label(label="SONOS PLAYLISTS")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("section-title")
        vbox.pack_start(title, False, False, 0)

        self.playlists_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.playlists_list_box)
        vbox.pack_start(scrolled, True, True, 0)

        return vbox

    def create_queue_view(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)

        title = Gtk.Label(label="CURRENT PLAY QUEUE")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("section-title")
        vbox.pack_start(title, False, False, 0)

        self.queue_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.queue_list_box)
        vbox.pack_start(scrolled, True, True, 0)

        return vbox

    # ----------------- NAVIGATION -----------------

    def make_nav_handler(self, view_id: str):
        def handler(button):
            self.set_active_nav(view_id)
        return handler

    def set_active_nav(self, view_id: str):
        self.stack.set_visible_child_name(view_id)
        for vid, btn in self.nav_buttons.items():
            ctx = btn.get_style_context()
            if vid == view_id:
                ctx.add_class("nav-button-active")
            else:
                ctx.remove_class("nav-button-active")

        # Lazy load content for selected tab
        if view_id == "favorites" and not self.favorites_data:
            self.run_async(self.load_favorites)
        elif view_id == "radio" and not self.radio_data:
            self.run_async(self.load_radio)
        elif view_id == "playlists" and not self.playlist_data:
            self.run_async(self.load_playlists)
        elif view_id == "queue":
            self.run_async(self.load_queue)

    # ----------------- CONTENT LOADERS -----------------

    def initial_discovery(self):
        self.manager.discover_fast()
        GLib.idle_add(self.update_rooms_ui)
        # Background load content
        self.load_favorites()
        self.load_radio()
        self.load_playlists()
        # Start regular poller thread
        threading.Thread(target=self.poll_loop, daemon=True).start()

    def refresh_all(self):
        self.manager.discover_fast()
        GLib.idle_add(self.update_rooms_ui)
        self.load_favorites()
        self.load_radio()
        self.load_playlists()
        self.load_queue()

    def load_favorites(self):
        spk = self.manager.active_speaker
        if not spk:
            return
        self.favorites_data = spk.get_favorites()
        GLib.idle_add(self.render_favorites, self.favorites_data)

    def render_favorites(self, items: List[Dict[str, Any]]):
        for child in self.favorites_list_box.get_children():
            self.favorites_list_box.remove(child)

        for it in items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("item-row")

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t_lbl = Gtk.Label(label=it["title"])
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.get_style_context().add_class("item-title")
            info.pack_start(t_lbl, False, False, 0)

            desc_text = it["desc"] if it["desc"] else "Favorite Item"
            d_lbl = Gtk.Label(label=desc_text)
            d_lbl.set_halign(Gtk.Align.START)
            d_lbl.get_style_context().add_class("item-desc")
            info.pack_start(d_lbl, False, False, 0)

            row.pack_start(info, True, True, 0)

            btn_play = Gtk.Button(label="Play ▶")
            btn_play.get_style_context().add_class("btn-play-item")
            btn_play.connect("clicked", self.make_play_item_handler(it))
            row.pack_end(btn_play, False, False, 0)

            self.favorites_list_box.pack_start(row, False, False, 0)

        self.favorites_list_box.show_all()

    def on_fav_search_changed(self, entry):
        query = entry.get_text().lower().strip()
        filtered = [f for f in self.favorites_data if query in f["title"].lower() or query in f["desc"].lower()]
        self.render_favorites(filtered)

    def load_radio(self):
        spk = self.manager.active_speaker
        if not spk:
            return
        # Combine TuneIn favorites and local presets
        radios = [f for f in self.favorites_data if "station" in f.get("desc", "").lower() or "radio" in f.get("desc", "").lower() or "stream" in f.get("uri", "").lower()]
        # Add R:0/0 stations
        extra_radios = spk.get_radios()
        for er in extra_radios:
            if not any(r["title"] == er["title"] for r in radios):
                radios.append(er)
        self.radio_data = radios
        GLib.idle_add(self.render_radio, self.radio_data)

    def render_radio(self, items: List[Dict[str, Any]]):
        for child in self.radio_list_box.get_children():
            self.radio_list_box.remove(child)

        for it in items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("item-row")

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t_lbl = Gtk.Label(label=it["title"])
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.get_style_context().add_class("item-title")
            info.pack_start(t_lbl, False, False, 0)

            d_lbl = Gtk.Label(label="Live Radio Stream")
            d_lbl.set_halign(Gtk.Align.START)
            d_lbl.get_style_context().add_class("item-desc")
            info.pack_start(d_lbl, False, False, 0)

            row.pack_start(info, True, True, 0)

            btn_play = Gtk.Button(label="Tune In 📻")
            btn_play.get_style_context().add_class("btn-play-item")
            btn_play.connect("clicked", self.make_play_item_handler(it))
            row.pack_end(btn_play, False, False, 0)

            self.radio_list_box.pack_start(row, False, False, 0)

        self.radio_list_box.show_all()

    def load_playlists(self):
        spk = self.manager.active_speaker
        if not spk:
            return
        self.playlist_data = spk.get_playlists()
        GLib.idle_add(self.render_playlists, self.playlist_data)

    def render_playlists(self, items: List[Dict[str, Any]]):
        for child in self.playlists_list_box.get_children():
            self.playlists_list_box.remove(child)

        for it in items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("item-row")

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t_lbl = Gtk.Label(label=it["title"])
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.get_style_context().add_class("item-title")
            info.pack_start(t_lbl, False, False, 0)

            d_lbl = Gtk.Label(label=it["desc"])
            d_lbl.set_halign(Gtk.Align.START)
            d_lbl.get_style_context().add_class("item-desc")
            info.pack_start(d_lbl, False, False, 0)

            row.pack_start(info, True, True, 0)

            btn_play = Gtk.Button(label="Play Playlist ▶")
            btn_play.get_style_context().add_class("btn-play-item")
            btn_play.connect("clicked", self.make_play_item_handler(it))
            row.pack_end(btn_play, False, False, 0)

            self.playlists_list_box.pack_start(row, False, False, 0)

        self.playlists_list_box.show_all()

    def load_queue(self):
        spk = self.manager.active_speaker
        if not spk:
            return
        self.queue_data = spk.get_queue()
        GLib.idle_add(self.render_queue, self.queue_data)

    def render_queue(self, items: List[Dict[str, Any]]):
        for child in self.queue_list_box.get_children():
            self.queue_list_box.remove(child)

        for it in items:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("item-row")

            num_lbl = Gtk.Label(label=f"{it['index'] + 1}.")
            num_lbl.set_size_request(28, -1)
            num_lbl.get_style_context().add_class("item-desc")
            row.pack_start(num_lbl, False, False, 0)

            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t_lbl = Gtk.Label(label=it["title"])
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.get_style_context().add_class("item-title")
            info.pack_start(t_lbl, False, False, 0)

            d_lbl = Gtk.Label(label=it.get("artist", ""))
            d_lbl.set_halign(Gtk.Align.START)
            d_lbl.get_style_context().add_class("item-desc")
            info.pack_start(d_lbl, False, False, 0)

            row.pack_start(info, True, True, 0)

            btn_play = Gtk.Button(label="Play ▶")
            btn_play.get_style_context().add_class("btn-play-item")
            btn_play.connect("clicked", self.make_queue_play_handler(it["index"]))
            row.pack_end(btn_play, False, False, 0)

            self.queue_list_box.pack_start(row, False, False, 0)

        self.queue_list_box.show_all()

    def make_play_item_handler(self, item: Dict[str, Any]):
        def handler(button):
            spk = self.manager.active_speaker
            if spk:
                self.run_async(lambda: spk.play_media_item(item))
                self.set_active_nav("now_playing")
        return handler

    def make_queue_play_handler(self, index: int):
        def handler(button):
            spk = self.manager.active_speaker
            if spk:
                self.run_async(lambda: spk.play_from_queue_index(index))
                self.set_active_nav("now_playing")
        return handler

    # ----------------- ROOMS & SYNC -----------------

    def update_rooms_ui(self):
        for child in self.rooms_box.get_children():
            self.rooms_box.remove(child)

        groups = self.manager.get_display_groups()
        for spk in groups:
            if len(spk.members) > 1:
                other_names = [m.name for m in spk.members if m.name != spk.name]
                display_name = f"{spk.name} (+{', '.join(other_names)})"
            else:
                display_name = spk.name

            btn = Gtk.Button(label=display_name)
            if btn.get_child():
                btn.get_child().set_halign(Gtk.Align.START)
            btn.get_style_context().add_class("room-button")
            if self.manager.active_speaker and self.manager.active_speaker.ip == spk.ip:
                btn.get_style_context().add_class("room-button-active")

            btn.connect("clicked", self.make_room_select_handler(spk))
            self.rooms_box.pack_start(btn, False, False, 0)

        self.rooms_box.show_all()
        if self.manager.active_speaker:
            self.lbl_room_indicator.set_text(f"ROOM: {self.manager.active_speaker.name.upper()}")

    def make_room_select_handler(self, spk: SonosSpeaker):
        def handler(button):
            self.manager.active_speaker = spk
            self.update_rooms_ui()
            # Refresh content for new room
            self.run_async(self.manager.poll_active)
            self.run_async(self.load_favorites)
            self.run_async(self.load_queue)
        return handler

    def set_default_album_art(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 240, 240)
        pixbuf.fill(0x24242eff)
        self.art_image.set_from_pixbuf(pixbuf)

    def poll_loop(self):
        while self.running:
            try:
                self.manager.poll_active()
                GLib.idle_add(self.update_player_ui)
            except Exception as e:
                pass
            time.sleep(1.0)

    def update_player_ui(self):
        spk = self.manager.active_speaker
        if not spk:
            return

        t = spk.current_track
        title = t.get("title", "No music playing")
        artist = t.get("artist", "")
        album = t.get("album", "")
        dur_sec = t.get("duration_sec", 0)
        pos_sec = t.get("position_sec", 0)

        self.lbl_title.set_text(title)
        self.lbl_artist.set_text(artist)
        self.lbl_album.set_text(album)

        self.lbl_mini_title.set_text(title)
        self.lbl_mini_artist.set_text(artist if artist else spk.name)

        self.lbl_rel_time.set_text(t.get("rel_time", "0:00"))
        self.lbl_duration.set_text(t.get("duration", "0:00"))

        if not self.is_slider_dragging and dur_sec > 0:
            self.seek_bar.set_range(0, dur_sec)
            self.seek_bar.set_value(pos_sec)

        if spk.state == "PLAYING":
            self.btn_play.set_label("⏸")
        else:
            self.btn_play.set_label("▶")

        if not self.is_slider_dragging:
            self.updating_volume = True
            self.volume_slider.set_value(spk.volume)
            self.updating_volume = False
            self.lbl_volume.set_text(f"{spk.volume}%")

        if spk.is_muted:
            self.btn_mute.set_label("🔇")
        else:
            self.btn_mute.set_label("🔊")

        art_url = t.get("art_url", "")
        if art_url != self.current_art_url:
            self.current_art_url = art_url
            if art_url:
                threading.Thread(target=self.load_album_art, args=(art_url,), daemon=True).start()
            else:
                self.set_default_album_art()

    def load_album_art(self, url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SonosLinux/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read()
            loader = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf:
                scaled = pixbuf.scale_simple(240, 240, GdkPixbuf.InterpType.BILINEAR)
                GLib.idle_add(self.art_image.set_from_pixbuf, scaled)
        except Exception:
            GLib.idle_add(self.set_default_album_art)

    def on_toggle_play(self, button):
        spk = self.manager.active_speaker
        if not spk:
            return
        if spk.state == "PLAYING":
            self.run_async(spk.pause)
            self.btn_play.set_label("▶")
        else:
            self.run_async(spk.play)
            self.btn_play.set_label("⏸")

    def on_toggle_mute(self, button):
        spk = self.manager.active_speaker
        if not spk:
            return
        new_mute = not spk.is_muted
        self.run_async(lambda: spk.set_mute(new_mute))
        self.btn_mute.set_label("🔇" if new_mute else "🔊")

    def on_volume_changed(self, scale):
        if getattr(self, "updating_volume", False):
            return
        val = int(scale.get_value())
        self.lbl_volume.set_text(f"{val}%")
        spk = self.manager.active_speaker
        if spk and abs(spk.volume - val) >= 1:
            self.run_async(lambda: spk.set_volume(val))

    def on_seek_press(self, scale, event):
        self.is_slider_dragging = True

    def on_seek_release(self, scale, event):
        self.is_slider_dragging = False
        val = int(scale.get_value())
        m = val // 60
        s = val % 60
        time_str = f"0:{m:02d}:{s:02d}"
        spk = self.manager.active_speaker
        if spk:
            self.run_async(lambda: spk.seek(time_str))

    def run_async(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def on_destroy(self, window):
        self.running = False
        Gtk.main_quit()

def main():
    app = SonosApp()
    app.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()

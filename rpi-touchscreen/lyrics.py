#!/usr/bin/env python3
"""
Synchronized lyrics fetcher via LRCLIB for Sonos Touchscreen.
"""

import json
import urllib.request
import urllib.parse
import re

USER_AGENT = "SonosTouchscreen/1.0 (Raspberry Pi Touch Controller)"

def clean_track_title(title: str) -> str:
    if not title:
        return ""
    cleaned = re.sub(r'\(.*?(remaster|deluxe|version|live|bonus|edit|feat\.|ft\.).*?\)', '', title, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[.*?\]', '', cleaned)
    cleaned = re.sub(r' - .*?Remaster.*', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def parse_lrc(lrc_text: str):
    lines = []
    if not lrc_text:
        return lines
    line_re = re.compile(r'\[(\d{2}):(\d{2}(?:\.\d{1,3})?)\](.*)')
    for row in lrc_text.splitlines():
        m = line_re.match(row.strip())
        if m:
            mins = int(m.group(1))
            secs = float(m.group(2))
            t = mins * 60 + secs
            text = m.group(3).strip()
            if text:
                lines.append({"time": round(t, 2), "text": text})
    lines.sort(key=lambda x: x["time"])
    return lines

def fetch_lyrics(title: str, artist: str, duration: float = 0, album: str = ""):
    if not title or not artist:
        return {"synced": False, "lines": [], "plain": ""}
    
    clean_title = clean_track_title(title)
    params = {
        "track_name": clean_title,
        "artist_name": artist
    }
    if duration > 10:
        params["duration"] = int(duration)
    if album:
        params["album_name"] = album

    query_str = urllib.parse.urlencode(params)
    url = f"https://lrclib.net/api/get?{query_str}"
    
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("syncedLyrics"):
                lines = parse_lrc(data["syncedLyrics"])
                return {
                    "synced": True,
                    "lines": lines,
                    "plain": data.get("plainLyrics", "")
                }
            elif data.get("plainLyrics"):
                return {
                    "synced": False,
                    "lines": [{"time": 0.0, "text": l} for l in data["plainLyrics"].splitlines() if l.strip()],
                    "plain": data["plainLyrics"]
                }
    except Exception:
        pass

    # Search fallback
    search_params = {"q": f"{clean_title} {artist}"}
    search_url = f"https://lrclib.net/api/search?{urllib.parse.urlencode(search_params)}"
    req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            results = json.loads(resp.read().decode("utf-8"))
            if results and isinstance(results, list):
                for item in results:
                    if item.get("syncedLyrics"):
                        return {
                            "synced": True,
                            "lines": parse_lrc(item["syncedLyrics"]),
                            "plain": item.get("plainLyrics", "")
                        }
    except Exception:
        pass

    return {"synced": False, "lines": [], "plain": ""}

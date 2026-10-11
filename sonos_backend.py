#!/usr/bin/env python3
"""
Sonos UPnP/SOAP Client Backend
Provides real-time discovery, control, ContentDirectory browsing, and metadata for Sonos sound systems on Linux.
"""

import os
import sys
import time
import socket
import html
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor

SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body>{body}</s:Body>'
    '</s:Envelope>'
)

class SonosSpeaker:
    def __init__(self, ip: str, name: str, uuid: str, is_coordinator: bool = True, group_id: str = ""):
        self.ip = ip
        self.name = name
        self.uuid = uuid
        self.is_coordinator = is_coordinator
        self.group_id = group_id
        self.coordinator_uuid = ""
        self.members: List['SonosSpeaker'] = []
        self.volume = 0
        self.is_muted = False
        self.state = "STOPPED"
        self.current_track = {
            "title": "No track playing",
            "artist": "",
            "album": "",
            "art_url": "",
            "duration": "0:00:00",
            "rel_time": "0:00:00",
            "position_sec": 0,
            "duration_sec": 0
        }

    def soap_call(self, service: str, action: str, body: str, timeout: float = 3.0) -> Optional[ET.Element]:
        url = f"http://{self.ip}:1400/{service}/Control"
        full_body = SOAP_ENVELOPE.format(body=body).encode("utf-8")
        headers = {
            "SOAPACTION": f'"urn:schemas-upnp-org:service:{service}:1#{action}"',
            "Content-Type": 'text/xml; charset="utf-8"',
            "User-Agent": "SonosLinux/1.0"
        }
        req = urllib.request.Request(url, data=full_body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                return ET.fromstring(data)
        except Exception:
            return None

    def play(self):
        body = '<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Play>'
        self.soap_call("MediaRenderer/AVTransport", "Play", body)

    def pause(self):
        body = '<u:Pause xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:Pause>'
        self.soap_call("MediaRenderer/AVTransport", "Pause", body)

    def stop(self):
        body = '<u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:Stop>'
        self.soap_call("MediaRenderer/AVTransport", "Stop", body)

    def next_track(self):
        body = '<u:Next xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:Next>'
        self.soap_call("MediaRenderer/AVTransport", "Next", body)

    def previous_track(self):
        body = '<u:Previous xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:Previous>'
        self.soap_call("MediaRenderer/AVTransport", "Previous", body)

    def set_volume(self, volume: int):
        volume = max(0, min(100, volume))
        body = (
            f'<u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">'
            f'<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume></u:SetVolume>'
        )
        self.soap_call("MediaRenderer/RenderingControl", "SetVolume", body)
        self.volume = volume

    def set_mute(self, mute: bool):
        val = 1 if mute else 0
        body = (
            f'<u:SetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">'
            f'<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredMute>{val}</DesiredMute></u:SetMute>'
        )
        self.soap_call("MediaRenderer/RenderingControl", "SetMute", body)
        self.is_muted = mute

    def seek(self, rel_time_str: str):
        body = (
            f'<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>{rel_time_str}</Target></u:Seek>'
        )
        self.soap_call("MediaRenderer/AVTransport", "Seek", body)

    def update_volume(self):
        body = '<u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetVolume>'
        root = self.soap_call("MediaRenderer/RenderingControl", "GetVolume", body)
        if root is not None:
            vol_elem = root.find(".//CurrentVolume")
            if vol_elem is not None and vol_elem.text:
                try:
                    self.volume = int(vol_elem.text)
                except ValueError:
                    pass

        body_mute = '<u:GetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetMute>'
        root_mute = self.soap_call("MediaRenderer/RenderingControl", "GetMute", body_mute)
        if root_mute is not None:
            mute_elem = root_mute.find(".//CurrentMute")
            if mute_elem is not None and mute_elem.text:
                self.is_muted = mute_elem.text == "1"

    def update_playback_state(self):
        body = '<u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:GetTransportInfo>'
        root = self.soap_call("MediaRenderer/AVTransport", "GetTransportInfo", body)
        if root is not None:
            state_elem = root.find(".//CurrentTransportState")
            if state_elem is not None and state_elem.text:
                self.state = state_elem.text

    def update_position_info(self):
        body = '<u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:GetPositionInfo>'
        root = self.soap_call("MediaRenderer/AVTransport", "GetPositionInfo", body)
        if root is None:
            return

        dur_elem = root.find(".//TrackDuration")
        rel_elem = root.find(".//RelTime")
        dur_str = dur_elem.text if dur_elem is not None and dur_elem.text else "0:00:00"
        rel_str = rel_elem.text if rel_elem is not None and rel_elem.text else "0:00:00"

        def parse_seconds(t_str: str) -> int:
            try:
                parts = t_str.split(":")
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
            except Exception:
                pass
            return 0

        self.current_track["duration"] = dur_str
        self.current_track["rel_time"] = rel_str
        self.current_track["position_sec"] = parse_seconds(rel_str)
        self.current_track["duration_sec"] = parse_seconds(dur_str)

        meta_elem = root.find(".//TrackMetaData")
        if meta_elem is not None and meta_elem.text and meta_elem.text != "NOT_IMPLEMENTED":
            try:
                mroot = ET.fromstring(meta_elem.text)
                title = mroot.find(".//{http://purl.org/dc/elements/1.1/}title")
                artist = mroot.find(".//{http://purl.org/dc/elements/1.1/}creator")
                album = mroot.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}album")
                art = mroot.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")

                self.current_track["title"] = title.text if title is not None and title.text else "Unknown Track"
                self.current_track["artist"] = artist.text if artist is not None and artist.text else ""
                self.current_track["album"] = album.text if album is not None and album.text else ""

                if art is not None and art.text:
                    art_uri = art.text
                    if art_uri.startswith("http"):
                        self.current_track["art_url"] = art_uri
                    else:
                        self.current_track["art_url"] = f"http://{self.ip}:1400{art_uri}"
                else:
                    self.current_track["art_url"] = ""
            except Exception:
                pass

    # -------------------------------------------------------------
    # ContentDirectory Browsing & Media Playback
    # -------------------------------------------------------------

    def browse_object(self, object_id: str, count: int = 100) -> List[Dict[str, Any]]:
        body = (
            f'<u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
            f'<ObjectID>{object_id}</ObjectID>'
            f'<BrowseFlag>BrowseDirectChildren</BrowseFlag>'
            f'<Filter>*</Filter>'
            f'<StartingIndex>0</StartingIndex>'
            f'<RequestedCount>{count}</RequestedCount>'
            f'<SortCriteria></SortCriteria>'
            f'</u:Browse>'
        )
        root = self.soap_call("MediaServer/ContentDirectory", "Browse", body, timeout=4.0)
        if root is None:
            return []

        res_elem = root.find(".//Result")
        if res_elem is None or not res_elem.text:
            return []

        items = []
        try:
            droot = ET.fromstring(res_elem.text)
            for idx, el in enumerate(droot.findall(".//*[@id]")):
                t = el.find(".//{http://purl.org/dc/elements/1.1/}title")
                r = el.find(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                md = el.find(".//{urn:schemas-rinconnetworks-com:metadata-1-0/}resMD")
                desc = el.find(".//{urn:schemas-rinconnetworks-com:metadata-1-0/}description")
                art = el.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                creator = el.find(".//{http://purl.org/dc/elements/1.1/}creator")

                uri_val = r.text if (r is not None and r.text) else ""
                art_val = art.text if (art is not None and art.text) else ""
                if art_val and not art_val.startswith("http"):
                    art_val = f"http://{self.ip}:1400{art_val}"

                items.append({
                    "id": el.attrib.get("id", str(idx)),
                    "index": idx,
                    "title": t.text if t is not None and t.text else "Unknown",
                    "uri": uri_val,
                    "meta": md.text if (md is not None and md.text) else "",
                    "desc": desc.text if (desc is not None and desc.text) else "",
                    "art": art_val,
                    "artist": creator.text if (creator is not None and creator.text) else ""
                })
        except Exception as e:
            print(f"Error parsing browse result for {object_id}:", e)
        return items

    def get_favorites(self) -> List[Dict[str, Any]]:
        return self.browse_object("FV:2", count=100)

    def get_playlists(self) -> List[Dict[str, Any]]:
        items = self.browse_object("SQ:", count=100)
        for it in items:
            it["desc"] = "Sonos Playlist"
        return items

    def get_radios(self) -> List[Dict[str, Any]]:
        items = self.browse_object("R:0/0", count=50)
        for it in items:
            it["desc"] = "Radio Station"
        return items

    def get_queue(self) -> List[Dict[str, Any]]:
        return self.browse_object("Q:0", count=100)

    def play_media_item(self, item: Dict[str, Any]):
        """Plays any item from Favorites, Radio, or Playlists."""
        uri = item.get("uri", "")
        meta = item.get("meta", "")
        esc_uri = html.escape(uri)
        esc_meta = html.escape(meta)

        # Radio streams and direct URLs
        if (
            uri.startswith("x-sonosapi-stream:") or
            uri.startswith("x-sonosapi-radio:") or
            uri.startswith("hls-radio:") or
            uri.startswith("x-rincon-mp3radio:") or
            uri.startswith("http://") or
            uri.startswith("https://")
        ):
            body_set = (
                f'<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
                f'<InstanceID>0</InstanceID>'
                f'<CurrentURI>{esc_uri}</CurrentURI>'
                f'<CurrentURIMetaData>{esc_meta}</CurrentURIMetaData>'
                f'</u:SetAVTransportURI>'
            )
            self.soap_call("MediaRenderer/AVTransport", "SetAVTransportURI", body_set)
            self.play()
            return

        # Playlists, containers, and queue items
        # 1. Clear existing queue
        body_clear = '<u:RemoveAllTracksFromQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:RemoveAllTracksFromQueue>'
        self.soap_call("MediaRenderer/AVTransport", "RemoveAllTracksFromQueue", body_clear)

        # 2. Add to queue
        body_add = (
            f'<u:AddURIToQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<InstanceID>0</InstanceID>'
            f'<EnqueuedURI>{esc_uri}</EnqueuedURI>'
            f'<EnqueuedURIMetaData>{esc_meta}</EnqueuedURIMetaData>'
            f'<DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued>'
            f'<EnqueueAsNext>0</EnqueueAsNext>'
            f'</u:AddURIToQueue>'
        )
        self.soap_call("MediaRenderer/AVTransport", "AddURIToQueue", body_add)

        # 3. Switch transport to queue and play from start
        queue_uri = f"x-rincon-queue:{self.uuid}#0"
        body_queue = (
            f'<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<InstanceID>0</InstanceID>'
            f'<CurrentURI>{queue_uri}</CurrentURI>'
            f'<CurrentURIMetaData></CurrentURIMetaData>'
            f'</u:SetAVTransportURI>'
        )
        self.soap_call("MediaRenderer/AVTransport", "SetAVTransportURI", body_queue)
        self.play()

    def play_from_queue_index(self, index: int):
        queue_uri = f"x-rincon-queue:{self.uuid}#0"
        body_queue = (
            f'<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<InstanceID>0</InstanceID>'
            f'<CurrentURI>{queue_uri}</CurrentURI>'
            f'<CurrentURIMetaData></CurrentURIMetaData>'
            f'</u:SetAVTransportURI>'
        )
        self.soap_call("MediaRenderer/AVTransport", "SetAVTransportURI", body_queue)

        body_seek = (
            f'<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<InstanceID>0</InstanceID>'
            f'<Unit>TRACK_NR</Unit>'
            f'<Target>{index + 1}</Target>'
            f'</u:Seek>'
        )
        self.soap_call("MediaRenderer/AVTransport", "Seek", body_seek)
        self.play()


class SonosManager:
    def __init__(self):
        self.speakers: Dict[str, SonosSpeaker] = {}
        self.active_speaker: Optional[SonosSpeaker] = None
        self.known_ips = []
        cache_file = os.path.expanduser("~/.config/sonos/speakers.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for ip, s in data.get("speakers", {}).items():
                        self.known_ips.append(ip)
                        name = s.get("name") or s.get("model") or f"Sonos ({ip})"
                        uid = s.get("udn") or ip
                        self.speakers[ip] = SonosSpeaker(ip, name, uid)
                    if self.speakers:
                        self.active_speaker = list(self.speakers.values())[0]
            except Exception:
                pass

    def discover_fast(self):
        candidates = list(self.known_ips)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                my_ip = s.getsockname()[0]
            prefix = ".".join(my_ip.split(".")[:3])
            for i in range(1, 255):
                ip = f"{prefix}.{i}"
                if ip not in candidates:
                    candidates.append(ip)
        except Exception:
            pass

        def probe(ip: str):
            try:
                url = f"http://{ip}:1400/status/zp"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        content = resp.read().decode("utf-8", errors="replace")
                        root = ET.fromstring(content)
                        zname = root.find(".//ZoneName")
                        uuid = root.find(".//LocalUID")
                        name = zname.text if zname is not None and zname.text else f"Sonos ({ip})"
                        uid = uuid.text if uuid is not None and uuid.text else ip
                        return ip, name, uid
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=30) as pool:
            results = pool.map(probe, candidates)
            for res in results:
                if res:
                    ip, name, uid = res
                    if ip not in self.speakers:
                        self.speakers[ip] = SonosSpeaker(ip, name, uid)

        self.refresh_topology()
        if not self.active_speaker and self.speakers:
            self.active_speaker = list(self.speakers.values())[0]

    def refresh_topology(self):
        if not self.speakers:
            return

        any_spk = list(self.speakers.values())[0]
        body = '<u:GetZoneGroupState xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1"></u:GetZoneGroupState>'
        root = any_spk.soap_call("ZoneGroupTopology", "GetZoneGroupState", body)
        if root is None:
            return

        state_elem = root.find(".//ZoneGroupState")
        if state_elem is None or not state_elem.text:
            return

        try:
            zroot = ET.fromstring(state_elem.text)
            for zg in zroot.findall(".//ZoneGroup"):
                coord_uuid = zg.attrib.get("Coordinator", "")
                group_id = zg.attrib.get("ID", "")
                members = zg.findall(".//ZoneGroupMember")

                member_spks = []
                for m in members:
                    loc = m.attrib.get("Location", "")
                    m_name = m.attrib.get("ZoneName", "")
                    m_uuid = m.attrib.get("UUID", "")
                    if "http://" in loc:
                        ip = loc.split("http://")[1].split(":")[0]
                        if ip not in self.speakers:
                            self.speakers[ip] = SonosSpeaker(ip, m_name, m_uuid)
                        spk = self.speakers[ip]
                        spk.name = m_name
                        spk.group_id = group_id
                        spk.coordinator_uuid = coord_uuid
                        spk.is_coordinator = (m_uuid == coord_uuid)
                        member_spks.append(spk)

                for spk in member_spks:
                    if spk.is_coordinator:
                        spk.members = member_spks
        except Exception as e:
            print("Topology parse error:", e)

    def get_display_groups(self) -> List[SonosSpeaker]:
        coordinators = [s for s in self.speakers.values() if s.is_coordinator]
        if not coordinators:
            return list(self.speakers.values())
        return coordinators

    def poll_active(self):
        if not self.active_speaker:
            return
        spk = self.active_speaker
        spk.update_playback_state()
        spk.update_position_info()
        spk.update_volume()

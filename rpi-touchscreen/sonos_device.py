#!/usr/bin/env python3
"""
Pure Python UPnP Sonos Device Controller & Household Tracker.
Zero external dependencies. Runs natively on Raspberry Pi (ARM / ARM64).
"""

import os
import json
import socket
import threading
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import html
import concurrent.futures

def parse_time(time_str: str) -> float:
    if not time_str or time_str in ("NOT_IMPLEMENTED", ""):
        return 0.0
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(time_str)
    except Exception:
        return 0.0

class SonosDeviceController:
    def __init__(self):
        self.lock = threading.Lock()
        self.speakers = {}            # room_name -> ip
        self._speaker_uuids = {}      # room_name -> RINCON_...
        self.active_room = ""
        self.active_ip = ""
        self.running = False
        self._active_group_members = []
        self._cache_file = os.path.expanduser("~/.local/share/sonos-touchscreen/speakers_cache.json")
        if not os.path.exists(os.path.dirname(self._cache_file)):
            self._cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speakers_cache.json")
        self._load_cache()

        self._last_state = {
            "room": "",
            "ip": "",
            "state": "STOPPED",
            "position": 0.0,
            "duration": 0.0,
            "title": "",
            "artist": "",
            "album": "",
            "albumArt": "",
            "volume": 0,
            "muted": False,
            "uri": "",
            "group_members": []
        }
        self.start()

    def _load_cache(self):
        try:
            candidates = [
                self._cache_file,
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "speakers_cache.json")
            ]
            for path in candidates:
                if os.path.exists(path):
                    with open(path, "r") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            cached_spk = data.get("speakers", {})
                            cached_uuids = data.get("uuids", {})
                            if cached_spk:
                                with self.lock:
                                    self.speakers.update(cached_spk)
                                    self._speaker_uuids.update(cached_uuids)
                                    if not self.active_room or self.active_room not in self.speakers:
                                        self.active_room = list(self.speakers.keys())[0]
                                        self.active_ip = self.speakers[self.active_room]
                                break
        except Exception:
            pass

    def _save_cache(self):
        try:
            with self.lock:
                data = {"speakers": dict(self.speakers), "uuids": dict(self._speaker_uuids)}
            d = os.path.dirname(self._cache_file)
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            with open(self._cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_state(self):
        with self.lock:
            return dict(self._last_state)

    def discover_speakers(self):
        """Discovers all Sonos speakers on the local subnet via ZoneGroupTopology and SSDP."""
        discovered = {}
        discovered_uuids = {}

        # 0. Check existing known speakers first via ZoneGroupTopology (ultra-fast <50ms)
        with self.lock:
            existing_ips = list(self.speakers.values())
            if self.active_ip and self.active_ip not in existing_ips:
                existing_ips.append(self.active_ip)

        for seed_ip in existing_ips:
            try:
                group_xml = self._soap_call(seed_ip, "/ZoneGroupTopology/Control", "ZoneGroupTopology", "GetZoneGroupState", timeout=2.0)
                if group_xml and "<ZoneGroupState>" in group_xml:
                    raw = group_xml.split("<ZoneGroupState>")[1].split("</ZoneGroupState>")[0]
                    root = ET.fromstring(html.unescape(raw))
                    for elem in root.iter():
                        if elem.tag == "ZoneGroupMember":
                            z_name = elem.attrib.get("ZoneName")
                            z_uuid = elem.attrib.get("UUID")
                            loc = elem.attrib.get("Location", "")
                            if loc and "://" in loc:
                                z_ip = loc.split("://")[1].split(":")[0]
                                if z_name and z_ip:
                                    discovered[z_name] = z_ip
                                    if z_uuid:
                                        discovered_uuids[z_name] = z_uuid
                    if len(discovered) >= 4:
                        break
            except Exception:
                pass

        # 1. SSDP Multicast Search
        msg = (
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n'
        )
        try:
            local_ip = ""
            try:
                temp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                temp_s.connect(('8.8.8.8', 80))
                local_ip = temp_s.getsockname()[0]
                temp_s.close()
            except Exception:
                pass

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if local_ip:
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
                except Exception:
                    pass
            s.settimeout(2.0)
            s.sendto(msg.encode("utf-8"), ("239.255.255.250", 1900))
            
            start = time.time()
            while time.time() - start < 2.0:
                try:
                    data, addr = s.recvfrom(2048)
                    ip = addr[0]
                    if ip not in discovered.values():
                        name = self._get_room_name(ip)
                        if name:
                            discovered[name] = ip
                except socket.timeout:
                    break
            s.close()
        except Exception:
            pass

        # 2. ZoneGroupTopology Expansion: Query GetZoneGroupState on all discovered IPs
        found_ips = list(discovered.values())
        for seed_ip in found_ips:
            try:
                group_xml = self._soap_call(seed_ip, "/ZoneGroupTopology/Control", "ZoneGroupTopology", "GetZoneGroupState", timeout=2.5)
                if group_xml and "<ZoneGroupState>" in group_xml:
                    raw = group_xml.split("<ZoneGroupState>")[1].split("</ZoneGroupState>")[0]
                    root = ET.fromstring(html.unescape(raw))
                    for elem in root.iter():
                        if elem.tag == "ZoneGroupMember":
                            z_name = elem.attrib.get("ZoneName")
                            z_uuid = elem.attrib.get("UUID")
                            loc = elem.attrib.get("Location", "")
                            if loc and "://" in loc:
                                z_ip = loc.split("://")[1].split(":")[0]
                                if z_name and z_ip:
                                    discovered[z_name] = z_ip
                                    if z_uuid:
                                        discovered_uuids[z_name] = z_uuid
            except Exception:
                continue

        with self.lock:
            self.speakers.update(discovered)
            self._speaker_uuids.update(discovered_uuids)
            if discovered and (not self.active_room or self.active_room not in self.speakers):
                self.active_room = list(self.speakers.keys())[0]
                self.active_ip = self.speakers[self.active_room]

        self._save_cache()

    def _get_room_name(self, ip: str) -> str:
        try:
            req = urllib.request.Request(f"http://{ip}:1400/xml/device_description.xml")
            with urllib.request.urlopen(req, timeout=1.5) as r:
                xml_txt = r.read().decode("utf-8", errors="ignore")
                if "<roomName>" in xml_txt:
                    return xml_txt.split("<roomName>")[1].split("</roomName>")[0].strip()
        except Exception:
            pass
        return ""

    def _soap_call(self, ip: str, endpoint: str, service: str, action: str, args: str = "", timeout: float = 3.5) -> str:
        if not ip:
            return ""
        body = f'''<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
            <s:Body>
                <u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">
                    <InstanceID>0</InstanceID>
                    {args}
                </u:{action}>
            </s:Body>
        </s:Envelope>'''
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"urn:schemas-upnp-org:service:{service}:1#{action}"'
        }
        req = urllib.request.Request(f"http://{ip}:1400{endpoint}", data=body.encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def set_active_room(self, room_name: str) -> bool:
        with self.lock:
            if room_name in self.speakers:
                self.active_room = room_name
                self.active_ip = self.speakers[room_name]
                return True
        return False

    def get_speakers_list(self):
        with self.lock:
            return [{"name": name, "ip": ip, "active": (name == self.active_room)} for name, ip in self.speakers.items()]

    def play(self):
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Play", "<Speed>1</Speed>")

    def pause(self):
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Pause")

    def stop(self):
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Stop")

    def next(self):
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Next")

    def previous(self):
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Previous")

    def seek(self, seconds: float):
        ip = self.active_ip
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        target = f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Seek", f"<Unit>REL_TIME</Unit><Target>{target}</Target>")

    def set_volume(self, volume: int):
        volume = max(0, min(100, int(volume)))
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "SetVolume", f"<Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>")

    def get_volume(self) -> int:
        ip = self.active_ip
        res = self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "GetVolume", "<Channel>Master</Channel>")
        if "<CurrentVolume>" in res:
            try:
                return int(res.split("<CurrentVolume>")[1].split("</CurrentVolume>")[0].strip())
            except Exception:
                pass
        return 0

    def set_mute(self, mute: bool):
        val = 1 if mute else 0
        ip = self.active_ip
        return self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "SetMute", f"<Channel>Master</Channel><DesiredMute>{val}</DesiredMute>")

    def get_mute(self) -> bool:
        ip = self.active_ip
        res = self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "GetMute", "<Channel>Master</Channel>")
        if "<CurrentMute>" in res:
            try:
                return res.split("<CurrentMute>")[1].split("</CurrentMute>")[0].strip() == "1"
            except Exception:
                pass
        return False

    def get_favorites(self):
        """Retrieves household Sonos Favorites, Radio Stations, and Saved Playlists."""
        ip = self.active_ip or (list(self.speakers.values())[0] if self.speakers else "")
        if not ip:
            return []
        
        favorites = []
        seen_titles = set()

        # 1. Sonos Favorites & Radio (FV:2)
        args_fav = '<ObjectID>FV:2</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag><Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>150</RequestedCount><SortCriteria></SortCriteria>'
        res_fav = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "Browse", args_fav, timeout=5.0)
        if "<Result>" in res_fav:
            try:
                inner_xml = html.unescape(res_fav.split("<Result>")[1].split("</Result>")[0])
                root = ET.fromstring(f"<root>{inner_xml}</root>")
                for item in root.findall(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item"):
                    try:
                        item_id = item.attrib.get("id", "")
                        title_elem = item.find("{http://purl.org/dc/elements/1.1/}title")
                        title = (title_elem.text or "").strip() if title_elem is not None and title_elem.text else "Favorite"
                        
                        art_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                        art = (art_elem.text or "").strip() if art_elem is not None and art_elem.text else ""
                        if art and art.startswith("/"):
                            art = f"http://{ip}:1400{art}"
                            
                        res_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                        uri = (res_elem.text or "").strip() if res_elem is not None and res_elem.text else ""
                        
                        meta_elem = item.find("{urn:schemas-rinconnetworks-com:metadata-1-0/}resMD")
                        if meta_elem is None:
                            meta_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}r:resMD")
                        meta = (meta_elem.text or "").strip() if meta_elem is not None and meta_elem.text else ""
                        
                        desc_elem = item.find("{urn:schemas-rinconnetworks-com:metadata-1-0/}description")
                        desc = (desc_elem.text or "").strip() if desc_elem is not None and desc_elem.text else ""

                        # If art is missing from parent, inspect meta
                        if not art and meta:
                            try:
                                m_root = ET.fromstring(html.unescape(meta) if not meta.startswith("<") else meta)
                                m_art = m_root.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                                if m_art is not None and m_art.text:
                                    art = m_art.text.strip()
                                    if art.startswith("/"):
                                        art = f"http://{ip}:1400{art}"
                            except Exception:
                                pass

                        # If uri is missing, inspect meta for inner item ID
                        if not uri and meta:
                            try:
                                m_root = ET.fromstring(html.unescape(meta) if not meta.startswith("<") else meta)
                                m_item = m_root.find(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item")
                                if m_item is not None:
                                    inner_id = m_item.attrib.get("id", "")
                                    if inner_id:
                                        uri = f"x-rincon-cpcontainer:{inner_id}"
                            except Exception:
                                pass

                        # Classify type
                        u_low = uri.lower()
                        t_low = title.lower()
                        d_low = desc.lower()
                        item_type = "favorite"
                        if "radio" in u_low or "radio" in t_low or "tunein" in u_low or "radio" in d_low or "radioprogram" in d_low or "podcast" in t_low:
                            item_type = "radio"
                        elif "playlist" in d_low or "playlist" in u_low or "album" in d_low:
                            item_type = "playlist"

                        is_container = uri.startswith("x-rincon-cpcontainer:") or "<upnp:class>object.container" in meta

                        seen_titles.add(title.strip().lower())
                        favorites.append({
                            "id": item_id,
                            "title": title,
                            "art": art,
                            "uri": uri,
                            "meta": meta,
                            "type": item_type,
                            "is_container": is_container,
                            "can_delete": True
                        })
                    except Exception:
                        continue
            except Exception:
                pass

        # 2. Sonos Playlists / Saved Queues (SQ:)
        args_sq = '<ObjectID>SQ:</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag><Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>50</RequestedCount><SortCriteria></SortCriteria>'
        res_sq = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "Browse", args_sq, timeout=4.0)
        if "<Result>" in res_sq:
            try:
                inner_xml = html.unescape(res_sq.split("<Result>")[1].split("</Result>")[0])
                root = ET.fromstring(f"<root>{inner_xml}</root>")
                for item in root.findall(".//*[@id]"):
                    try:
                        item_id = item.attrib.get("id", "")
                        title_elem = item.find("{http://purl.org/dc/elements/1.1/}title")
                        title = (title_elem.text or "").strip() if title_elem is not None and title_elem.text else "Playlist"
                        if title.strip().lower() in seen_titles:
                            continue
                        res_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                        uri = (res_elem.text or "").strip() if res_elem is not None and res_elem.text else ""
                        favorites.append({
                            "id": item_id,
                            "title": title,
                            "art": "",
                            "uri": uri,
                            "meta": "",
                            "type": "playlist",
                            "is_container": True,
                            "can_delete": False
                        })
                    except Exception:
                        continue
            except Exception:
                pass

        return favorites

    def add_favorite(self, title: str, uri: str, meta: str = "", art: str = "") -> bool:
        """Creates a new favorite item in Sonos FV:2."""
        ip = self.active_ip or (list(self.speakers.values())[0] if self.speakers else "")
        if not ip or not title or not uri:
            return False

        art_tag = f"<upnp:albumArtURI>{html.escape(art)}</upnp:albumArtURI>" if art else ""
        meta_tag = f"<r:resMD>{html.escape(meta)}</r:resMD>" if meta else ""

        if uri.startswith("x-sonosapi-radio:") or uri.startswith("x-rincon-mp3radio:") or uri.startswith("http:") or uri.startswith("https:"):
            protocol = "http-get:*:audio/mpeg:*"
            upnp_class = "object.item.sonos-favorite"
        elif uri.startswith("x-rincon-cpcontainer:"):
            protocol = "x-rincon-cpcontainer:*:*:*"
            upnp_class = "object.item.sonos-favorite"
        else:
            protocol = "*:*:*:*"
            upnp_class = "object.item.sonos-favorite"

        didl = (
            '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
            'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
            'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            f'<item id="" parentID="FV:2" restricted="true">'
            f'<dc:title>{html.escape(title)}</dc:title>'
            f'<upnp:class>{upnp_class}</upnp:class>'
            f'<res protocolInfo="{protocol}">{html.escape(uri)}</res>'
            f'{art_tag}'
            f'{meta_tag}'
            f'</item></DIDL-Lite>'
        )
        args = f'<ContainerID>FV:2</ContainerID><Elements>{html.escape(didl)}</Elements>'
        res = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "CreateObject", args)
        return "<ObjectID>" in res

    def add_current_to_favorites(self) -> dict:
        """Adds the currently playing track, radio station, or stream to Sonos Favorites."""
        ip = self.active_ip
        if not ip:
            return {"success": False, "error": "No active speaker"}

        st = self.get_state()
        title = st.get("title", "")
        artist = st.get("artist", "")
        fav_title = f"{title} – {artist}" if (artist and artist not in title) else title
        if not fav_title:
            return {"success": False, "error": "Nothing currently playing"}

        art = st.get("albumArt", "")
        
        pos_xml = self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "GetPositionInfo")
        track_uri = pos_xml.split("<TrackURI>")[1].split("</TrackURI>")[0] if "<TrackURI>" in pos_xml else ""
        track_meta = pos_xml.split("<TrackMetaData>")[1].split("</TrackMetaData>")[0] if "<TrackMetaData>" in pos_xml else ""

        if not track_uri:
            media_xml = self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "GetMediaInfo")
            track_uri = media_xml.split("<CurrentURI>")[1].split("</CurrentURI>")[0] if "<CurrentURI>" in media_xml else ""
            track_meta = media_xml.split("<CurrentURIMetaData>")[1].split("</CurrentURIMetaData>")[0] if "<CurrentURIMetaData>" in media_xml else ""

        if not track_uri:
            return {"success": False, "error": "Could not determine playing stream URI"}

        success = self.add_favorite(fav_title, track_uri, track_meta, art)
        return {"success": success, "title": fav_title}

    def delete_favorite(self, object_id: str) -> bool:
        """Deletes a favorite from Sonos FV:2."""
        ip = self.active_ip or (list(self.speakers.values())[0] if self.speakers else "")
        if not ip or not object_id:
            return False
        res = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "DestroyObject", f"<ObjectID>{html.escape(object_id)}</ObjectID>")
        return "<DestroyObjectResponse" in res

    def play_uri(self, uri: str, meta: str = ""):
        ip = self.active_ip
        escaped_meta = html.escape(meta)
        args = f"<CurrentURI>{html.escape(uri)}</CurrentURI><CurrentURIMetaData>{escaped_meta}</CurrentURIMetaData>"
        self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "SetAVTransportURI", args)
        return self.play()

    def _get_speaker_uuid(self, ip: str) -> str:
        try:
            req = urllib.request.Request(f"http://{ip}:1400/xml/device_description.xml")
            with urllib.request.urlopen(req, timeout=1.5) as r:
                xml_txt = r.read().decode("utf-8", errors="ignore")
                if "<UDN>uuid:" in xml_txt:
                    return xml_txt.split("<UDN>uuid:")[1].split("</UDN>")[0].strip()
        except Exception:
            pass
        return ""

    def get_volume_for_ip(self, ip: str) -> int:
        if not ip:
            return 0
        res = self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "GetVolume", "<Channel>Master</Channel>")
        if "<CurrentVolume>" in res:
            try:
                return int(res.split("<CurrentVolume>")[1].split("</CurrentVolume>")[0].strip())
            except Exception:
                pass
        return 0

    def get_mute_for_ip(self, ip: str) -> bool:
        if not ip:
            return False
        res = self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "GetMute", "<Channel>Master</Channel>")
        if "<CurrentMute>" in res:
            try:
                return res.split("<CurrentMute>")[1].split("</CurrentMute>")[0].strip() == "1"
            except Exception:
                pass
        return False

    def set_room_volume(self, room_name: str, volume: int):
        with self.lock:
            ip = self.speakers.get(room_name, self.active_ip)
        volume = max(0, min(100, int(volume)))
        return self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "SetVolume", f"<Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>")

    def set_room_mute(self, room_name: str, mute: bool):
        with self.lock:
            ip = self.speakers.get(room_name, self.active_ip)
        val = 1 if mute else 0
        return self._soap_call(ip, "/MediaRenderer/RenderingControl/Control", "RenderingControl", "SetMute", f"<Channel>Master</Channel><DesiredMute>{val}</DesiredMute>")

    def get_topology(self):
        """Retrieves household zone groups, member speakers, grouping status, and volumes."""
        with self.lock:
            active_room = self.active_room
            speakers = dict(self.speakers)
            seed_ip = self.active_ip or (list(speakers.values())[0] if speakers else "")

        if not seed_ip:
            return {"active_room": active_room, "active_member_count": 1, "rooms": self.get_speakers_list(), "groups": []}

        res = self._soap_call(seed_ip, "/ZoneGroupTopology/Control", "ZoneGroupTopology", "GetZoneGroupState")
        if "<ZoneGroupState>" not in res:
            return {"active_room": active_room, "active_member_count": 1, "rooms": self.get_speakers_list(), "groups": []}

        try:
            raw_state = res.split("<ZoneGroupState>")[1].split("</ZoneGroupState>")[0]
            inner_xml = html.unescape(raw_state)
            root = ET.fromstring(inner_xml)
            groups = []
            rooms_map = {}
            active_coord_uuid = ""

            for zg in root.findall(".//ZoneGroup"):
                coord_uuid = zg.attrib.get("Coordinator", "")
                group_id = zg.attrib.get("ID", "")
                members = []
                coord_name = ""

                for m in zg.findall("ZoneGroupMember"):
                    name = m.attrib.get("ZoneName", "")
                    uuid = m.attrib.get("UUID", "")
                    loc = m.attrib.get("Location", "")
                    mem_ip = loc.split("://")[1].split(":")[0] if "://" in loc else ""
                    is_coord = (uuid == coord_uuid)
                    if is_coord:
                        coord_name = name

                    with self.lock:
                        if name:
                            self._speaker_uuids[name] = uuid
                            if name not in self.speakers and mem_ip:
                                self.speakers[name] = mem_ip

                    member_info = {
                        "name": name,
                        "uuid": uuid,
                        "ip": mem_ip,
                        "is_coordinator": is_coord,
                        "group_id": group_id
                    }
                    members.append(member_info)
                    rooms_map[name] = member_info

                is_active_group = any(m["name"] == active_room for m in members)
                if is_active_group:
                    active_coord_uuid = coord_uuid

                groups.append({
                    "group_id": group_id,
                    "coordinator_uuid": coord_uuid,
                    "coordinator_name": coord_name,
                    "members": members,
                    "is_active_group": is_active_group
                })

            active_group = next((g for g in groups if g["is_active_group"]), None)
            active_members = [m["name"] for m in active_group["members"]] if active_group else ([active_room] if active_room else [])
            active_member_count = len(active_members)

            # Ensure all rooms from ZoneGroupState and self.speakers are present
            with self.lock:
                for name, meta in rooms_map.items():
                    if meta.get("ip"):
                        self.speakers[name] = meta["ip"]
                        if meta.get("uuid"):
                            self._speaker_uuids[name] = meta["uuid"]
                all_room_names = list(rooms_map.keys())
                for name in self.speakers.keys():
                    if name not in all_room_names:
                        all_room_names.append(name)

            decorated_rooms = []
            for name in all_room_names:
                room_meta = rooms_map.get(name, {})
                ip = room_meta.get("ip") or self.speakers.get(name, "")
                uuid = room_meta.get("uuid") or self._speaker_uuids.get(name, "")
                is_active = (name == active_room)
                is_in_active_group = (name in active_members)
                is_grouped = (active_member_count > 1) if is_active else is_in_active_group
                
                vol = self.get_volume_for_ip(ip) if ip else 0
                muted = self.get_mute_for_ip(ip) if ip else False

                decorated_rooms.append({
                    "name": name,
                    "ip": ip,
                    "uuid": uuid,
                    "is_active": is_active,
                    "is_coordinator": room_meta.get("is_coordinator", False),
                    "is_grouped": is_grouped,
                    "group_id": room_meta.get("group_id", ""),
                    "volume": vol,
                    "muted": muted
                })

            with self.lock:
                self._active_group_members = active_members

            return {
                "active_room": active_room,
                "active_member_count": active_member_count,
                "rooms": decorated_rooms,
                "groups": groups
            }
        except Exception:
            return {"active_room": active_room, "active_member_count": 1, "rooms": self.get_speakers_list(), "groups": []}

    def group_speaker(self, member_room: str, coordinator_room: str = None) -> bool:
        """Groups member_room to play in sync with coordinator_room."""
        coord_name = coordinator_room or self.active_room
        if member_room == coord_name:
            return True

        with self.lock:
            member_ip = self.speakers.get(member_room, "")
            coord_ip = self.speakers.get(coord_name, self.active_ip)
            coord_uuid = self._speaker_uuids.get(coord_name, "")

        if not coord_uuid and coord_ip:
            coord_uuid = self._get_speaker_uuid(coord_ip)
            with self.lock:
                self._speaker_uuids[coord_name] = coord_uuid

        if not member_ip or not coord_uuid:
            return False

        uri = f"x-rincon:{coord_uuid}"
        res = self._soap_call(member_ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "SetAVTransportURI", f"<CurrentURI>{uri}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>")
        success = "SetAVTransportURIResponse" in res
        if success:
            threading.Thread(target=self.get_topology, daemon=True).start()
        return success

    def ungroup_speaker(self, member_room: str) -> bool:
        """Ungroups member_room so it becomes a standalone playback zone."""
        with self.lock:
            member_ip = self.speakers.get(member_room, "")

        if not member_ip:
            return False

        res = self._soap_call(member_ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "BecomeCoordinatorOfStandaloneGroup")
        success = "BecomeCoordinatorOfStandaloneGroupResponse" in res
        if success:
            threading.Thread(target=self.get_topology, daemon=True).start()
        return success

    def group_all(self, coordinator_room: str = None) -> bool:
        """Groups all speakers to play together in sync."""
        coord_name = coordinator_room or self.active_room
        with self.lock:
            rooms = [r for r in self.speakers.keys() if r != coord_name]

        success = True
        for r in rooms:
            if not self.group_speaker(r, coord_name):
                success = False
        threading.Thread(target=self.get_topology, daemon=True).start()
        return success

    def ungroup_all(self) -> bool:
        """Separates all speakers into standalone rooms."""
        with self.lock:
            rooms = list(self.speakers.keys())

        for r in rooms:
            self.ungroup_speaker(r)
        threading.Thread(target=self.get_topology, daemon=True).start()
        return True

    def search_music(self, query: str, category: str = "all"):
        """Searches Sonos Music Library (artists, songs, albums) and Sonos Favorites."""
        if not query or not query.strip():
            return {"artists": [], "tracks": [], "albums": [], "favorites": []}

        query = query.strip()
        escaped = urllib.parse.quote(query, safe="")
        results = {"artists": [], "tracks": [], "albums": [], "favorites": []}

        # 1. Artists search
        if category in ("all", "artists"):
            results["artists"] = self._browse_didl(f"A:ARTIST:{escaped}", count=25)

        # 2. Tracks / Songs search
        if category in ("all", "tracks", "songs"):
            results["tracks"] = self._browse_didl(f"A:TRACKS:{escaped}", count=35)

        # 3. Albums search
        if category in ("all", "albums"):
            results["albums"] = self._browse_didl(f"A:ALBUM:{escaped}", count=25)

        # 4. Favorites & Radio matching
        if category in ("all", "favorites", "radio"):
            all_favs = self.get_favorites()
            q_lower = query.lower()
            results["favorites"] = [f for f in all_favs if q_lower in f.get("title", "").lower()]

        return results

    def browse_container(self, container_id: str):
        """Browses a container (e.g. an artist's albums or an album's tracks)."""
        return self._browse_didl(container_id, count=100)

    def _browse_didl(self, obj_id: str, count: int = 35):
        ip = self.active_ip or (list(self.speakers.values())[0] if self.speakers else "")
        if not ip:
            return []

        args = f'<ObjectID>{obj_id}</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag><Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>{count}</RequestedCount><SortCriteria></SortCriteria>'
        res = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "Browse", args)
        if '<Result>' not in res:
            return []

        xml = html.unescape(res.split('<Result>')[1].split('</Result>')[0])
        try:
            root = ET.fromstring(f'<root>{xml}</root>')
            items = []
            for el in root.findall('.//*[@id]'):
                item_id = el.attrib.get('id', '')
                title = el.findtext('{http://purl.org/dc/elements/1.1/}title') or ''
                artist = el.findtext('{http://purl.org/dc/elements/1.1/}creator') or ''
                album = el.findtext('{urn:schemas-upnp-org:metadata-1-0/upnp/}album') or ''
                art = el.findtext('{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI') or ''
                if art and art.startswith('/'):
                    art = f'http://{ip}:1400{art}'
                res_el = el.find('{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')
                uri = res_el.text if res_el is not None else ''
                is_container = el.tag.endswith('container')
                dur = res_el.attrib.get('duration', '') if res_el is not None else ''

                items.append({
                    'id': item_id,
                    'title': title,
                    'artist': artist,
                    'album': album,
                    'art': art,
                    'uri': uri,
                    'duration': dur,
                    'is_container': is_container
                })
            return items
        except Exception:
            return []

    def play_item(self, uri: str = "", meta: str = "", is_container: bool = False, item_id: str = ""):
        """Plays a track, album, artist, or favorite immediately on the active speaker / group."""
        ip = self.active_ip
        if not ip:
            return False

        if is_container:
            coord_uuid = self._speaker_uuids.get(self.active_room, "") or self._get_speaker_uuid(ip)
            target_uri = uri or f"x-rincon-playlist:{coord_uuid}#{item_id}"
            
            # Clear existing queue so selected container plays cleanly
            self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "RemoveAllTracksFromQueue")
            
            args = f'<EnqueuedURI>{html.escape(target_uri)}</EnqueuedURI><EnqueuedURIMetaData>{html.escape(meta)}</EnqueuedURIMetaData><DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued><EnqueueAsNext>0</EnqueueAsNext>'
            self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "AddURIToQueue", args)
            
            queue_uri = f"x-rincon-queue:{coord_uuid}#0"
            self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "SetAVTransportURI", f"<CurrentURI>{queue_uri}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>")
            self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "Seek", "<Unit>TRACK_NR</Unit><Target>1</Target>")
            self.play()
            return True
        else:
            if uri:
                self.play_uri(uri, meta)
                return True
        return False

    def queue_item(self, uri: str = "", meta: str = "", is_container: bool = False, item_id: str = ""):
        """Adds a track, album, or artist to the queue without stopping current playback."""
        ip = self.active_ip
        if not ip:
            return False

        coord_uuid = self._speaker_uuids.get(self.active_room, "") or self._get_speaker_uuid(ip)
        target_uri = uri or (f"x-rincon-playlist:{coord_uuid}#{item_id}" if is_container else "")
        if not target_uri:
            return False

        args = f'<EnqueuedURI>{html.escape(target_uri)}</EnqueuedURI><EnqueuedURIMetaData>{html.escape(meta)}</EnqueuedURIMetaData><DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued><EnqueueAsNext>0</EnqueueAsNext>'
        res = self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "AddURIToQueue", args)
        return "<AddURIToQueueResponse" in res

    def query_state(self):
        with self.lock:
            ip = self.active_ip
            current_room = self.active_room
            fallback_state = dict(self._last_state)

        if not ip:
            return fallback_state

        # 1. Transport State
        trans = self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "GetTransportInfo")
        state = "STOPPED"
        if "<CurrentTransportState>" in trans:
            state = trans.split("<CurrentTransportState>")[1].split("</CurrentTransportState>")[0].strip()

        # 2. Position & Track Info
        pos_xml = self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "GetPositionInfo")
        title, artist, album, art = "", "", "", ""
        rel_time = 0.0
        duration = 0.0

        if pos_xml:
            if "<RelTime>" in pos_xml:
                rel_time = parse_time(pos_xml.split("<RelTime>")[1].split("</RelTime>")[0])
            if "<TrackDuration>" in pos_xml:
                duration = parse_time(pos_xml.split("<TrackDuration>")[1].split("</TrackDuration>")[0])
            if "<TrackMetaData>" in pos_xml:
                meta = html.unescape(pos_xml.split("<TrackMetaData>")[1].split("</TrackMetaData>")[0])
                if "<dc:title>" in meta:
                    title = html.unescape(meta.split("<dc:title>")[1].split("</dc:title>")[0])
                if "<dc:creator>" in meta:
                    artist = html.unescape(meta.split("<dc:creator>")[1].split("</dc:creator>")[0])
                if "<upnp:album>" in meta:
                    album = html.unescape(meta.split("<upnp:album>")[1].split("</upnp:album>")[0])
                if "<upnp:albumArtURI>" in meta:
                    art = html.unescape(meta.split("<upnp:albumArtURI>")[1].split("</upnp:albumArtURI>")[0])
                    if art.startswith("/"):
                        art = f"http://{ip}:1400{art}"

        # 3. Volume & Mute
        vol = self.get_volume()
        muted = self.get_mute()

        with self.lock:
            group_members = list(self._active_group_members) if self._active_group_members else ([current_room] if current_room else [])

        st = {
            "room": current_room,
            "ip": ip,
            "state": state,
            "position": rel_time,
            "duration": duration,
            "title": title,
            "artist": artist,
            "album": album,
            "albumArt": art,
            "volume": vol,
            "muted": muted,
            "group_members": group_members
        }
        with self.lock:
            self._last_state = st
        return st

    def start(self):
        self.running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        last_discovery_time = 0
        last_auto_follow_time = 0
        while self.running:
            now = time.time()
            need_discovery = False
            with self.lock:
                if not self.speakers:
                    if now - last_discovery_time > 3.0:
                        need_discovery = True
                else:
                    if now - last_discovery_time > 60.0:
                        need_discovery = True

            if need_discovery:
                last_discovery_time = now
                try:
                    self.discover_speakers()
                except Exception:
                    pass

            try:
                self.query_state()
            except Exception:
                pass

            try:
                cur = self.get_state()
                if cur.get("state") != "PLAYING" and (now - last_auto_follow_time > 10.0):
                    last_auto_follow_time = now
                    with self.lock:
                        spkrs = list(self.speakers.items())
                    for r_name, r_ip in spkrs:
                        if r_name == self.active_room:
                            continue
                        trans = self._soap_call(r_ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "GetTransportInfo")
                        if "<CurrentTransportState>PLAYING</CurrentTransportState>" in trans:
                            with self.lock:
                                self.active_room = r_name
                                self.active_ip = r_ip
                            break
            except Exception:
                pass

            time.sleep(0.8)

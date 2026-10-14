#!/usr/bin/env python3
"""
Pure Python UPnP Sonos Device Controller & Household Tracker.
Zero external dependencies. Runs natively on Raspberry Pi (ARM / ARM64).
"""

import socket
import threading
import time
import urllib.request
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
        self.speakers = {}      # room_name -> ip
        self.active_room = ""
        self.active_ip = ""
        self.running = False
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
            "uri": ""
        }
        self.start()

    def get_state(self):
        with self.lock:
            return dict(self._last_state)

    def discover_speakers(self):
        """Discovers all Sonos speakers on the local subnet via SSDP and ZoneGroupTopology."""
        discovered = {}
        # 1. SSDP Multicast Search
        msg = (
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n'
        )
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
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

        # 2. ZoneGroupTopology Expansion
        found_ips = list(discovered.values())
        for seed_ip in found_ips:
            try:
                xml_data = self._soap_call(seed_ip, "/ZoneGroupTopology/Control", "ZoneGroupTopology", "GetZoneGroupAttributes")
                if xml_data and "CurrentZoneGroupName" in xml_data:
                    group_xml = self._soap_call(seed_ip, "/ZoneGroupTopology/Control", "ZoneGroupTopology", "GetZoneGroupState")
                    if group_xml:
                        root = ET.fromstring(group_xml)
                        for elem in root.iter():
                            if elem.tag == "ZoneGroupMember":
                                z_name = elem.attrib.get("ZoneName")
                                loc = elem.attrib.get("Location", "")
                                if loc and "://" in loc:
                                    z_ip = loc.split("://")[1].split(":")[0]
                                    if z_name and z_ip:
                                        discovered[z_name] = z_ip
                if len(discovered) > len(found_ips):
                    break
            except Exception:
                continue

        with self.lock:
            self.speakers = discovered
            if discovered and (not self.active_room or self.active_room not in discovered):
                self.active_room = list(discovered.keys())[0]
                self.active_ip = discovered[self.active_room]

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

    def _soap_call(self, ip: str, endpoint: str, service: str, action: str, args: str = "") -> str:
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
            with urllib.request.urlopen(req, timeout=2.0) as resp:
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
        """Retrieves household Sonos Favorites / Radio Stations."""
        ip = self.active_ip or (list(self.speakers.values())[0] if self.speakers else "")
        if not ip:
            return []
        
        args = '<ObjectID>FV:2</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag><Filter>*</Filter><StartingIndex>0</StartingIndex><RequestedCount>30</RequestedCount><SortCriteria></SortCriteria>'
        res = self._soap_call(ip, "/MediaServer/ContentDirectory/Control", "ContentDirectory", "Browse", args)
        favorites = []
        if "<Result>" in res:
            inner_xml = html.unescape(res.split("<Result>")[1].split("</Result>")[0])
            try:
                root = ET.fromstring(f"<root>{inner_xml}</root>")
                for item in root.findall(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item"):
                    title_elem = item.find("{http://purl.org/dc/elements/1.1/}title")
                    title = title_elem.text if title_elem is not None else "Favorite"
                    art_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                    art = art_elem.text if art_elem is not None else ""
                    if art and art.startswith("/"):
                        art = f"http://{ip}:1400{art}"
                    res_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                    uri = res_elem.text if res_elem is not None else ""
                    meta_elem = item.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}r:resMD")
                    meta = meta_elem.text if meta_elem is not None else ""
                    favorites.append({
                        "title": title,
                        "art": art,
                        "uri": uri,
                        "meta": meta
                    })
            except Exception:
                pass
        return favorites

    def play_uri(self, uri: str, meta: str = ""):
        ip = self.active_ip
        escaped_meta = html.escape(meta)
        args = f"<CurrentURI>{html.escape(uri)}</CurrentURI><CurrentURIMetaData>{escaped_meta}</CurrentURIMetaData>"
        self._soap_call(ip, "/MediaRenderer/AVTransport/Control", "AVTransport", "SetAVTransportURI", args)
        return self.play()

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
            "muted": muted
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

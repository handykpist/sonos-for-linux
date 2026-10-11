#!/usr/bin/env python3
"""
Sonos SSDP Discovery Bridge for Linux
Auto-discovers Sonos speakers dynamically using multi-tier SSDP multicast,
fast port-1400 LAN scan fallback, and UPnP ZoneGroupTopology expansion.
Relays announcements to local Wine / Sonos.exe controllers without hardcoded IPs or names.
"""

import os
import re
import sys
import time
import json
import socket
import struct
import html
import threading
import urllib.request
import xml.etree.ElementTree as ET
import concurrent.futures

CONFIG_DIR = os.path.expanduser("~/.config/sonos")
CACHE_FILE = os.path.join(CONFIG_DIR, "speakers.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

def get_local_subnet():
    """Detects local IP and /24 subnet prefix."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            my_ip = s.getsockname()[0]
        prefix = ".".join(my_ip.split(".")[:3])
        return my_ip, prefix
    except Exception:
        return "127.0.0.1", "127.0.0"

class SonosSsdpBridge:
    def __init__(self):
        self.speakers = {}
        self.household_id = ""
        self.lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.speakers = data.get("speakers", {})
                    self.household_id = data.get("household_id", "")
                    if self.speakers:
                        print(f"[*] Loaded {len(self.speakers)} cached Sonos speakers.")
            except Exception:
                pass

    def _save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "household_id": self.household_id,
                    "speakers": self.speakers,
                    "updated_at": time.time()
                }, f, indent=2)
        except Exception:
            pass

    def discover_all(self):
        """Multi-tier discovery: SSDP Multicast -> LAN Port 1400 Scan -> ZoneGroupTopology."""
        seed_ips = set()

        # Tier 1: SSDP Multicast M-SEARCH
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.5)
            msg = (
                "M-SEARCH * HTTP/1.1\r\n"
                "HOST: 239.255.255.250:1900\r\n"
                "MAN: \"ssdp:discover\"\r\n"
                "MX: 1\r\n"
                "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n"
            ).encode("utf-8")
            sock.sendto(msg, ("239.255.255.250", 1900))

            start = time.time()
            while time.time() - start < 2.0:
                try:
                    data, addr = sock.recvfrom(2048)
                    text = data.decode("utf-8", errors="ignore")
                    if ":1400" in text or "Sonos" in text or "ZonePlayer" in text:
                        seed_ips.add(addr[0])
                except socket.timeout:
                    break
                except Exception:
                    break
            sock.close()
        except Exception as e:
            print(f"[!] SSDP search note: {e}")

        # Tier 2: Fast LAN Port 1400 Probe (if SSDP multicast yielded nothing or incomplete)
        if len(seed_ips) == 0:
            _, prefix = get_local_subnet()
            def probe(ip):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.2)
                try:
                    if s.connect_ex((ip, 1400)) == 0:
                        return ip
                except Exception:
                    pass
                finally:
                    s.close()
                return None

            candidates = [f"{prefix}.{i}" for i in range(1, 255)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
                for res in ex.map(probe, candidates):
                    if res:
                        seed_ips.add(res)

        # Tier 3: Expand Whole Household via ZoneGroupTopology from any seed IP
        for ip in list(seed_ips):
            try:
                body = (
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                    '<s:Body><u:GetZoneGroupState xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1"></u:GetZoneGroupState></s:Body>'
                    '</s:Envelope>'
                )
                headers = {
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPACTION": '"urn:schemas-upnp-org:service:ZoneGroupTopology:1#GetZoneGroupState"'
                }
                req = urllib.request.Request(f"http://{ip}:1400/ZoneGroupTopology/Control", data=body.encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req, timeout=2.5) as r:
                    xml_str = r.read().decode("utf-8", errors="ignore")
                    start = xml_str.find("<ZoneGroupState>")
                    end = xml_str.find("</ZoneGroupState>")
                    if start != -1 and end != -1:
                        raw = html.unescape(xml_str[start+16:end])
                        root = ET.fromstring(raw)
                        for zg in root.findall(".//ZoneGroupMember"):
                            zname = zg.attrib.get("ZoneName", "Sonos Speaker")
                            loc = zg.attrib.get("Location", "")
                            uuid = zg.attrib.get("UUID", "")
                            m = re.search(r"http://([^:/]+)", loc)
                            spk_ip = m.group(1) if m else ip

                            with self.lock:
                                self.speakers[spk_ip] = {
                                    "ip": spk_ip,
                                    "name": zname,
                                    "location": loc or f"http://{spk_ip}:1400/xml/device_description.xml",
                                    "udn": f"uuid:{uuid}" if not uuid.startswith("uuid:") else uuid,
                                    "model": "ZonePlayer",
                                    "server": "Linux UPnP/1.0 Sonos/57.23-74170"
                                }
                        if self.speakers:
                            print(f"[+] Successfully auto-discovered {len(self.speakers)} Sonos speakers!")
                            self._save_cache()
                            break
            except Exception:
                continue

    def make_response(self, spk, st):
        hh = self.household_id or "Sonos_Household"
        udn = spk.get("udn", f"uuid:RINCON_{spk['ip'].replace('.', '')}")
        return (
            f"HTTP/1.1 200 OK\r\n"
            f"CACHE-CONTROL: max-age=1800\r\n"
            f"EXT:\r\n"
            f"LOCATION: {spk['location']}\r\n"
            f"SERVER: {spk['server']}\r\n"
            f"ST: {st}\r\n"
            f"USN: {udn}::{st}\r\n"
            f"X-RINCON-BOOTSEQ: 1\r\n"
            f"X-RINCON-HOUSEHOLD: {hh}\r\n"
            f"\r\n"
        ).encode("utf-8")

    def make_notify(self, spk, nt):
        hh = self.household_id or "Sonos_Household"
        udn = spk.get("udn", f"uuid:RINCON_{spk['ip'].replace('.', '')}")
        return (
            f"NOTIFY * HTTP/1.1\r\n"
            f"HOST: 239.255.255.250:1900\r\n"
            f"CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {spk['location']}\r\n"
            f"NT: {nt}\r\n"
            f"NTS: ssdp:alive\r\n"
            f"SERVER: {spk['server']}\r\n"
            f"USN: {udn}::{nt}\r\n"
            f"X-RINCON-BOOTSEQ: 1\r\n"
            f"X-RINCON-HOUSEHOLD: {hh}\r\n"
            f"\r\n"
        ).encode("utf-8")

    def run(self):
        # Auto-discover speakers on start
        self.discover_all()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass

        try:
            sock.bind(("", 1900))
        except Exception as e:
            print(f"[!] Warning: Could not bind 0.0.0.0:1900 ({e})")
            return

        try:
            mreq = struct.pack("4s4s", socket.inet_aton("239.255.255.250"), socket.inet_aton("0.0.0.0"))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception as e:
            print(f"[!] Multicast join notice: {e}")

        print("[*] Sonos SSDP Bridge active and listening on port 1900...")

        # Background announcer & periodic re-discovery thread
        def background_worker():
            while True:
                time.sleep(3.0)
                if not self.speakers:
                    self.discover_all()
                    continue

                with self.lock:
                    active_speakers = list(self.speakers.values())

                for spk in active_speakers:
                    data = self.make_notify(spk, "urn:schemas-upnp-org:device:ZonePlayer:1")
                    try:
                        sock.sendto(data, ("239.255.255.250", 1900))
                        sock.sendto(data, ("127.0.0.1", 1900))
                    except Exception:
                        pass

        t = threading.Thread(target=background_worker, daemon=True)
        t.start()

        types = [
            "urn:schemas-upnp-org:device:ZonePlayer:1",
            "upnp:rootdevice",
            "ssdp:all"
        ]

        while True:
            try:
                data, addr = sock.recvfrom(2048)
                msg = data.decode("utf-8", errors="replace")

                # Passive discovery of newly connected speakers
                if "NOTIFY" in msg and ("ZonePlayer" in msg or ":1400" in msg):
                    loc_m = re.search(r"LOCATION:\s*(http://[^\r\n]+)", msg, re.IGNORECASE)
                    if loc_m and addr[0] not in self.speakers:
                        print(f"[+] Detected speaker announcement from {addr[0]}")
                        self.discover_all()

                # Reply to M-SEARCH from Sonos.exe
                if "M-SEARCH" in msg:
                    with self.lock:
                        speaker_list = list(self.speakers.values())
                    for spk in speaker_list:
                        for st in types:
                            resp = self.make_response(spk, st)
                            sock.sendto(resp, addr)
            except Exception:
                time.sleep(0.5)

if __name__ == "__main__":
    bridge = SonosSsdpBridge()
    bridge.run()

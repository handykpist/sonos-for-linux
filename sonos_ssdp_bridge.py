#!/usr/bin/env python3
"""
Sonos SSDP Discovery Bridge for Linux
Dynamically discovers Sonos speakers on the local network and relays announcements
directly to local controllers (Wine / Sonos.exe), resolving Linux firewall (UFW)
and multicast routing limitations without requiring hardcoded IP addresses or device names.
"""

import os
import sys
import re
import time
import json
import socket
import struct
import threading
import urllib.request
import xml.etree.ElementTree as ET

CONFIG_DIR = os.path.expanduser("~/.config/sonos")
CACHE_FILE = os.path.join(CONFIG_DIR, "speakers.json")
os.makedirs(CONFIG_DIR, exist_ok=True)

class SonosSsdpBridge:
    def __init__(self):
        self.speakers = {}
        self.household_id = ""
        self.lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        """Loads cached speaker descriptors if available."""
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
        """Persists discovered speakers to local user cache."""
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "household_id": self.household_id,
                    "speakers": self.speakers,
                    "updated_at": time.time()
                }, f, indent=2)
        except Exception:
            pass

    def discover_network(self):
        """Sends an active SSDP M-SEARCH query to discover Sonos hardware on the LAN."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2.5)

        msg = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            "MAN: \"ssdp:discover\"\r\n"
            "MX: 1\r\n"
            "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n\r\n"
        ).encode("utf-8")

        try:
            sock.sendto(msg, ("239.255.255.250", 1900))
        except Exception as e:
            print(f"[!] Warning sending SSDP search: {e}")
            sock.close()
            return

        start = time.time()
        new_found = False
        while time.time() - start < 3.0:
            try:
                data, addr = sock.recvfrom(2048)
                ip = addr[0]
                text = data.decode("utf-8", errors="ignore")

                # Verify it's a Sonos device
                if "Sonos" not in text and "ZonePlayer" not in text and ":1400" not in text:
                    continue

                loc_match = re.search(r"LOCATION:\s*(http://[^\r\n]+)", text, re.IGNORECASE)
                hh_match = re.search(r"X-RINCON-HOUSEHOLD:\s*([^\r\n]+)", text, re.IGNORECASE)
                usn_match = re.search(r"USN:\s*([^\r\n]+)", text, re.IGNORECASE)
                server_match = re.search(r"SERVER:\s*([^\r\n]+)", text, re.IGNORECASE)

                if loc_match:
                    loc = loc_match.group(1).strip()
                    hh = hh_match.group(1).strip() if hh_match else ""
                    usn = usn_match.group(1).split("::")[0].strip() if usn_match else f"uuid:RINCON_{ip.replace('.', '')}"
                    server = server_match.group(1).strip() if server_match else "Linux UPnP/1.0 Sonos/57.23-74170"

                    model = "ZonePlayer"
                    m = re.search(r"\(([^)]+)\)", server)
                    if m:
                        model = m.group(1)

                    with self.lock:
                        if ip not in self.speakers:
                            new_found = True
                            print(f"[+] Discovered Sonos speaker at {ip} ({model})")
                        self.speakers[ip] = {
                            "ip": ip,
                            "location": loc,
                            "udn": usn,
                            "household": hh,
                            "model": model,
                            "server": server
                        }
                        if hh and not self.household_id:
                            self.household_id = hh

            except socket.timeout:
                break
            except Exception:
                break
        sock.close()

        if new_found:
            self._save_cache()

    def make_response(self, spk, st):
        hh = spk.get("household") or self.household_id or "Sonos_Generic"
        return (
            f"HTTP/1.1 200 OK\r\n"
            f"CACHE-CONTROL: max-age=1800\r\n"
            f"EXT:\r\n"
            f"LOCATION: {spk['location']}\r\n"
            f"SERVER: {spk['server']}\r\n"
            f"ST: {st}\r\n"
            f"USN: {spk['udn']}::{st}\r\n"
            f"X-RINCON-BOOTSEQ: 1\r\n"
            f"X-RINCON-HOUSEHOLD: {hh}\r\n"
            f"\r\n"
        ).encode("utf-8")

    def make_notify(self, spk, nt):
        hh = spk.get("household") or self.household_id or "Sonos_Generic"
        return (
            f"NOTIFY * HTTP/1.1\r\n"
            f"HOST: 239.255.255.250:1900\r\n"
            f"CACHE-CONTROL: max-age=1800\r\n"
            f"LOCATION: {spk['location']}\r\n"
            f"NT: {nt}\r\n"
            f"NTS: ssdp:alive\r\n"
            f"SERVER: {spk['server']}\r\n"
            f"USN: {spk['udn']}::{nt}\r\n"
            f"X-RINCON-BOOTSEQ: 1\r\n"
            f"X-RINCON-HOUSEHOLD: {hh}\r\n"
            f"\r\n"
        ).encode("utf-8")

    def run(self):
        # Initial active discovery
        self.discover_network()

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
            print(f"[!] Warning joining multicast: {e}")

        print("[*] Sonos SSDP Bridge active and listening on port 1900...")

        # Periodic background announcer & re-discovery thread
        def background_worker():
            while True:
                time.sleep(3.0)
                # If no speakers known, try discovering again
                if not self.speakers:
                    self.discover_network()
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

        # Listen for M-SEARCH queries from Sonos.exe
        types = [
            "urn:schemas-upnp-org:device:ZonePlayer:1",
            "upnp:rootdevice",
            "ssdp:all"
        ]

        while True:
            try:
                data, addr = sock.recvfrom(2048)
                msg = data.decode("utf-8", errors="replace")
                if "M-SEARCH" in msg:
                    with self.lock:
                        speaker_list = list(self.speakers.values())
                    for spk in speaker_list:
                        for st in types:
                            resp = self.make_response(spk, st)
                            sock.sendto(resp, addr)
            except Exception as e:
                time.sleep(0.5)

if __name__ == "__main__":
    bridge = SonosSsdpBridge()
    bridge.run()

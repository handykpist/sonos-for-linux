#!/usr/bin/env python3
"""
Sonos Touchscreen Controller Server for Raspberry Pi (800x480).
Serves the responsive touch interface and provides REST API for playback, volume, and lyrics.
"""

import os
import sys
import json
import socket
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer

from sonos_device import SonosDeviceController
from lyrics import fetch_lyrics

PORT = 5000
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

LOCAL_IP = get_local_ip()

class TouchscreenHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress routine GET logging for performance on Raspberry Pi
        return

    def do_GET(self):
        try:
            url_parts = self.path.split("?")
            path = url_parts[0]
            
            if path in ("/", "/index.html"):
                self.serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
                return
            elif path == "/style.css":
                self.serve_file(os.path.join(STATIC_DIR, "style.css"), "text/css; charset=utf-8")
                return
            elif path == "/app.js":
                self.serve_file(os.path.join(STATIC_DIR, "app.js"), "application/javascript; charset=utf-8")
                return
            elif path == "/api/status":
                st = self.server.controller.get_state()
                self.send_json(st)
                return
            elif path == "/api/speakers":
                speakers = self.server.controller.get_speakers_list()
                active = self.server.controller.active_room
                self.send_json({"speakers": speakers, "active": active})
                return
            elif path == "/api/favorites":
                favs = self.server.controller.get_favorites()
                self.send_json({"favorites": favs})
                return
            elif path == "/api/lyrics":
                st = self.server.controller.get_state()
                lyrics = fetch_lyrics(st.get("title", ""), st.get("artist", ""), st.get("duration", 0), st.get("album", ""))
                self.send_json(lyrics)
                return
            elif path == "/api/albumart":
                st = self.server.controller.get_state()
                art_url = st.get("albumArt", "")
                if art_url:
                    try:
                        req = urllib.request.Request(art_url, headers={"User-Agent": "SonosTouchscreen/1.0"})
                        with urllib.request.urlopen(req, timeout=2.0) as resp:
                            data = resp.read()
                            ctype = resp.headers.get("Content-Type", "image/jpeg")
                            self.send_response(200)
                            self.send_header("Content-Type", ctype)
                            self.send_header("Content-Length", str(len(data)))
                            self.send_header("Cache-Control", "public, max-age=86400")
                            self.end_headers()
                            self.wfile.write(data)
                            return
                    except Exception:
                        pass
                self.send_error(404, "Album Art Not Found")
                return
            elif path == "/api/update/status":
                base_dir = os.path.dirname(os.path.abspath(__file__))
                log_file = os.path.join(base_dir, "update.log")
                recent_log = []
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r") as f:
                            recent_log = [line.strip() for line in f.readlines()[-15:] if line.strip()]
                    except Exception:
                        pass
                self.send_json({"log": recent_log})
                return

            super().do_GET()
        except Exception as e:
            try:
                self.send_error(500, f"Server Error: {str(e)}")
            except Exception:
                pass

    def do_POST(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                payload = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                payload = {}

            path = self.path

            if path == "/api/speaker":
                room = payload.get("room", "")
                success = self.server.controller.set_active_room(room)
                self.send_json({"success": success, "active": self.server.controller.active_room})
                return
            elif path == "/api/play":
                self.server.controller.play()
                self.send_json({"success": True})
                return
            elif path == "/api/pause":
                self.server.controller.pause()
                self.send_json({"success": True})
                return
            elif path == "/api/playpause":
                st = self.server.controller.get_state()
                if st.get("state") == "PLAYING":
                    self.server.controller.pause()
                else:
                    self.server.controller.play()
                self.send_json({"success": True})
                return
            elif path == "/api/next":
                self.server.controller.next()
                self.send_json({"success": True})
                return
            elif path == "/api/prev":
                self.server.controller.previous()
                self.send_json({"success": True})
                return
            elif path == "/api/volume":
                vol = payload.get("volume", 0)
                self.server.controller.set_volume(vol)
                self.send_json({"success": True, "volume": vol})
                return
            elif path == "/api/mute":
                current_mute = self.server.controller.get_mute()
                new_mute = not current_mute
                self.server.controller.set_mute(new_mute)
                self.send_json({"success": True, "muted": new_mute})
                return
            elif path == "/api/seek":
                pos = float(payload.get("position", 0.0))
                self.server.controller.seek(pos)
                self.send_json({"success": True, "position": pos})
                return
            elif path == "/api/favorite/play":
                uri = payload.get("uri", "")
                meta = payload.get("meta", "")
                self.server.controller.play_uri(uri, meta)
                self.send_json({"success": True})
                return
            elif path == "/api/update/trigger":
                import subprocess
                base_dir = os.path.dirname(os.path.abspath(__file__))
                script_path = os.path.join(base_dir, "kiosk", "auto_update.sh")
                if os.path.exists(script_path):
                    subprocess.Popen(["bash", script_path, "--force"])
                    self.send_json({"success": True, "message": "Auto-update triggered in background"})
                else:
                    self.send_json({"success": False, "error": "Update script not found"}, status=404)
                return
            elif path == "/api/system/exit":
                import subprocess, threading
                def _exit():
                    import time
                    time.sleep(0.3)
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    script = os.path.join(base_dir, "kiosk", "exit_kiosk.sh")
                    if os.path.exists(script):
                        subprocess.run(["bash", script])
                    else:
                        os.system("systemctl --user stop sonos-touchscreen 2>/dev/null || true")
                        os.system("killall -9 chromium-browser chromium google-chrome 2>/dev/null || true")
                        os.system("pkill -9 -f 'chromium.*5000' 2>/dev/null || true")
                        os.system("pkill -9 -f 'server.py' 2>/dev/null || true")
                threading.Thread(target=_exit, daemon=True).start()
                self.send_json({"success": True, "message": "Exiting kiosk to desktop..."})
                return
            elif path == "/api/system/restart":
                import threading, time
                def _restart():
                    time.sleep(0.4)
                    os.system("systemctl --user restart sonos-touchscreen 2>/dev/null")
                threading.Thread(target=_restart, daemon=True).start()
                self.send_json({"success": True, "message": "Restarting Sonos App..."})
                return
            elif path == "/api/system/reboot":
                import threading, time
                def _reboot():
                    time.sleep(0.5)
                    os.system("sudo reboot 2>/dev/null || systemctl reboot 2>/dev/null")
                threading.Thread(target=_reboot, daemon=True).start()
                self.send_json({"success": True, "message": "Rebooting Raspberry Pi..."})
                return
            elif path == "/api/system/shutdown":
                import threading, time
                def _shutdown():
                    time.sleep(0.5)
                    os.system("sudo shutdown -h now 2>/dev/null || systemctl poweroff 2>/dev/null")
                threading.Thread(target=_shutdown, daemon=True).start()
                self.send_json({"success": True, "message": "Shutting down Raspberry Pi..."})
                return

            self.send_error(404, "Endpoint Not Found")
        except Exception as e:
            try:
                self.send_error(500, f"Server Error: {str(e)}")
            except Exception:
                pass

    def serve_file(self, full_path, content_type):
        if not os.path.exists(full_path):
            self.send_error(404, "File Not Found")
            return
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

class TouchscreenServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.controller = SonosDeviceController()

def run():
    server_address = ("", PORT)
    httpd = TouchscreenServer(server_address, TouchscreenHandler)
    print("=" * 60)
    print("      Sonos Touchscreen Controller (Raspberry Pi)      ")
    print(f"     Local Kiosk URL: http://localhost:{PORT}")
    print(f"     Network URL:     http://{LOCAL_IP}:{PORT}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Sonos Touchscreen Server...")
        httpd.server_close()

if __name__ == "__main__":
    run()

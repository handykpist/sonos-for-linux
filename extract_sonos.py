#!/usr/bin/env python3
"""
Sonos Windows Installer Reverse-Engineering Extractor
Extracts and decrypts components from Sonos_57.23-74170.exe on Linux.

Reverse-engineered format:
- PE32 InstallShield SFX container
- Encrypted InstallShield stream with 44 component descriptors
- Key derived via seed ^ [0x13, 0x35, 0x86, 0x07]
- 4-bit nibble rotation + inversion byte cipher
- Zlib compressed stream containing Microsoft Windows Installer database (MSI)
- Embedded Data1.cab containing .NET / WPF application assemblies and resources
"""

import os
import sys
import zlib
import struct
import subprocess
import shutil

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALLER_EXE = os.path.join(PROJECT_DIR, "Sonos_57.23-74170.exe")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "extracted")
TEMP_DIR = os.path.join(OUTPUT_DIR, ".tmp")

MAGIC_DEC = [0x13, 0x35, 0x86, 0x07]

def gen_key(seed: bytes) -> bytes:
    return bytes([seed[i] ^ MAGIC_DEC[i % 4] for i in range(len(seed))])

def decode_byte(b: int, k: int) -> int:
    rot = ((b << 4) & 0xF0) | ((b >> 4) & 0x0F)
    return (~(k ^ rot)) & 0xFF

def extract_installer_payload():
    print(f"[*] Step 1: Extracting payload from {os.path.basename(INSTALLER_EXE)}...")
    os.makedirs(TEMP_DIR, exist_ok=True)
    subprocess.run(["7z", "x", INSTALLER_EXE, f"-o{TEMP_DIR}", "-y"], check=True, stdout=subprocess.DEVNULL)
    payload_path = os.path.join(TEMP_DIR, "[0]")
    if not os.path.isfile(payload_path):
        raise FileNotFoundError(f"Could not find InstallShield payload '[0]' in {TEMP_DIR}")
    return payload_path

def decrypt_msi(payload_path: str, msi_out_path: str):
    print("[*] Step 2: Decrypting and decompressing Sonos Controller.msi...")
    with open(payload_path, "rb") as f:
        hdr = f.read(46)
        sig = hdr[:14]
        if not sig.startswith(b"InstallShield"):
            raise ValueError(f"Invalid InstallShield signature: {sig}")
        
        num_files, typ = struct.unpack("<HI", hdr[14:20])
        print(f"    Detected InstallShield archive with {num_files} components.")
        
        # Scan files in header
        msi_offset = None
        msi_size = None
        for i in range(num_files):
            pos = f.tell()
            fhdr = f.read(312)
            if len(fhdr) < 312:
                break
            fname = fhdr[:260].split(b"\x00")[0].decode("latin1", errors="replace")
            size = struct.unpack("<I", fhdr[268:272])[0]
            data_pos = f.tell()
            if "Sonos Controller.msi" in fname:
                msi_offset = data_pos
                msi_size = size
                break
            f.seek(data_pos + size)

        if msi_offset is None or msi_size is None:
            raise RuntimeError("Sonos Controller.msi not found in payload table.")

        print(f"    Found 'Sonos Controller.msi' at 0x{msi_offset:x} ({msi_size} bytes). Decrypting...")
        f.seek(msi_offset)
        key = gen_key(b"Sonos Controller.msi")
        decompressor = zlib.decompressobj()

        left = msi_size
        with open(msi_out_path, "wb") as out_f:
            while left > 0:
                chunk_len = min(left, 64 * 1024)
                raw = f.read(chunk_len)
                if not raw:
                    break
                decoded_chunk = bytearray(len(raw))
                done_so_far = msi_size - left
                for i in range(len(raw)):
                    in_block = (done_so_far + i) % 1024
                    decoded_chunk[i] = decode_byte(raw[i], key[in_block % len(key)])
                out_f.write(decompressor.decompress(bytes(decoded_chunk)))
                left -= len(raw)
            out_f.write(decompressor.flush())

    print(f"    Successfully decrypted MSI ({os.path.getsize(msi_out_path)} bytes) -> {msi_out_path}")

def extract_app_files(msi_path: str):
    print("[*] Step 3: Extracting application assemblies and files from MSI...")
    app_dir = os.path.join(OUTPUT_DIR, "app")
    os.makedirs(app_dir, exist_ok=True)
    
    # Extract Data1.cab from MSI
    cab_path = os.path.join(TEMP_DIR, "Data1.cab")
    subprocess.run(["7z", "e", msi_path, "Data1.cab", f"-o{TEMP_DIR}", "-y"], check=True, stdout=subprocess.DEVNULL)
    
    # Extract Data1.cab contents
    subprocess.run(["7z", "x", cab_path, f"-o{app_dir}", "-y"], check=True, stdout=subprocess.DEVNULL)
    print(f"    Extracted {len(os.listdir(app_dir))} files into {app_dir}")

def extract_icons(msi_path: str):
    print("[*] Step 4: Extracting icons...")
    icons_dir = os.path.join(OUTPUT_DIR, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    subprocess.run(["7z", "e", msi_path, "Icon.*", f"-o{TEMP_DIR}", "-y"], check=True, stdout=subprocess.DEVNULL)
    
    # Find the icon PE file
    icon_pe = None
    for item in os.listdir(TEMP_DIR):
        if item.startswith("Icon.Sonos.exe") and item.endswith(".exe"):
            icon_pe = os.path.join(TEMP_DIR, item)
            break
            
    if icon_pe:
        # Extract 256x256 PNG icon
        subprocess.run(["7z", "e", icon_pe, ".rsrc/0/ICON/9", f"-o{icons_dir}", "-y"], stdout=subprocess.DEVNULL)
        extracted_png = os.path.join(icons_dir, "9")
        if os.path.exists(extracted_png):
            target_png = os.path.join(OUTPUT_DIR, "sonos-256.png")
            shutil.move(extracted_png, target_png)
            print(f"    Saved high-resolution Sonos icon to {target_png}")

def cleanup():
    if os.path.isdir(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

def main():
    if not os.path.isfile(INSTALLER_EXE):
        print(f"Error: Installer {INSTALLER_EXE} not found.")
        sys.exit(1)
        
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    msi_path = os.path.join(OUTPUT_DIR, "SonosController.msi")
    
    try:
        payload = extract_installer_payload()
        decrypt_msi(payload, msi_path)
        extract_app_files(msi_path)
        extract_icons(msi_path)
        cleanup()
        print("\n[+] Done! Sonos components have been successfully extracted and decrypted.")
        print(f"    Target directory: {OUTPUT_DIR}/")
    except Exception as e:
        print(f"\n[!] Extraction failed: {e}")
        cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()


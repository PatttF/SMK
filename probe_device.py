#!/usr/bin/env python3
"""Probe the SMK25 for device ID, flash read, and heartbeat messages."""

import rtmidi
import time
import sys
import os

# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

def encode_7bit(data):
    result = bytearray()
    acc = 0
    bits = 0
    for byte in data:
        acc |= (byte << bits)
        bits += 8
        while bits >= 7:
            result.append(acc & 0x7F)
            acc >>= 7
            bits -= 7
    if bits > 0:
        result.append(acc & 0x7F)
    return bytes(result)

def decode_7bit(encoded, expected_len):
    acc = 0
    bits = 0
    result = bytearray()
    for byte in encoded:
        acc |= (byte & 0x7F) << bits
        bits += 7
        while bits >= 8 and len(result) < expected_len:
            result.append(acc & 0xFF)
            acc >>= 8
            bits -= 8
    return bytes(result)

def hex_str(data, limit=80):
    s = " ".join(f"{b:02X}" for b in data)
    if len(s) > limit:
        s = s[:limit] + "..."
    return s

def open_port(name, cls):
    port = cls()
    for i, p in enumerate(port.get_ports()):
        if name in p:
            port.open_port(i)
            return port
    return None

def drain(mi, label=""):
    """Read all pending messages."""
    msgs = []
    while True:
        r = mi.get_message()
        if not r:
            break
        data, dt = r
        msgs.append(data)
        if label:
            print(f"  {label}: ({len(data)}B) {hex_str(data)}")
    return msgs

def send_sysex(mo, raw_payload):
    encoded = encode_7bit(raw_payload)
    msg = [0xF0] + list(encoded) + [0xF7]
    mo.send_message(msg)

# -------------------------------------------------------
# Open ports
# -------------------------------------------------------
mo = open_port("Private", rtmidi.MidiOut)
mi = open_port("Private", rtmidi.MidiIn)

if not mo or not mi:
    print("ERROR: Could not open SINCO Private port")
    sys.exit(1)

print("Ports opened. Draining any pending messages...")
time.sleep(0.3)
drain(mi, "pending")

# -------------------------------------------------------
# Test 1: Listen for heartbeat (1-2 seconds)
# -------------------------------------------------------
print("\n=== Listening for heartbeat (2 seconds) ===")
start = time.time()
heartbeats = []
while time.time() - start < 2.5:
    r = mi.get_message()
    if r:
        data, dt = r
        heartbeats.append(data)
        print(f"  Received: ({len(data)}B) {hex_str(data)}")
    time.sleep(0.01)
if not heartbeats:
    print("  No heartbeat detected")

# -------------------------------------------------------
# Test 2: Device ID query (command 0x11)
# -------------------------------------------------------
print("\n=== Device ID Query (cmd 0x11) ===")
query = bytes([0x00, 0x59, 0x11, 0x00, 0x00, 0x00, 0xFF])
send_sysex(mo, query)
time.sleep(0.5)

responses = drain(mi)
for data in responses:
    print(f"  Response ({len(data)}B): {hex_str(data)}")
    if len(data) > 2 and data[0] == 0xF0 and data[-1] == 0xF7:
        inner = bytes(data[1:-1])
        for try_len in range(30, 5, -1):
            decoded = decode_7bit(inner, try_len)
            text_chars = [chr(b) if 32 <= b < 127 else '.' for b in decoded]
            text = ''.join(text_chars)
            if 'SMK' in text or 'SINCO' in text or 'SMC' in text:
                print(f"  Decoded text: {text}")
                print(f"  Decoded hex:  {hex_str(decoded)}")
                break
        else:
            # Just show a few decode lengths
            for tl in [27, 20, 15]:
                decoded = decode_7bit(inner, tl)
                print(f"  Decoded ({tl}): {hex_str(decoded)}")

if not responses:
    print("  No response")

# -------------------------------------------------------
# Test 3: Flash read, FlashType 4 (device header, 12 bytes)
# -------------------------------------------------------
print("\n=== Flash Read: FlashType 4 (device header) ===")
body = bytes([
    0x04,                    # FlashType 4
    0x00, 0x00, 0x00, 0x00,  # addr = 0
    0x0C, 0x00, 0x00,        # length = 12
])
cs = (~sum(body)) & 0xFF
raw = bytes([0x00, 0x59, 0x23, 0x08, 0x00, 0x00]) + body + bytes([cs])
send_sysex(mo, raw)
time.sleep(0.5)

responses = drain(mi)
for data in responses:
    print(f"  Response ({len(data)}B): {hex_str(data)}")
    if len(data) > 2 and data[0] == 0xF0 and data[-1] == 0xF7:
        inner = bytes(data[1:-1])
        # Response should be data_len + 0x0F = 12 + 15 = 27 decoded bytes
        decoded = decode_7bit(inner, 27)
        print(f"  Decoded (27): {hex_str(decoded)}")
        # The response echoes the header, then has data starting after offset ~14
        if len(decoded) >= 21:
            header_data = decoded[14:14+12]
            print(f"  Header data:  {hex_str(header_data)}")
            print(f"    Byte 0x07 (boot preset): 0x{header_data[7]:02X}" if len(header_data) > 7 else "")
            print(f"    Byte 0x0A (preset idx):  0x{header_data[10]:02X}" if len(header_data) > 10 else "")
if not responses:
    print("  No response")

# -------------------------------------------------------
# Test 4: Flash read, FlashType 5, first 64 bytes of preset 8
# -------------------------------------------------------
print("\n=== Flash Read: FlashType 5 (preset 8 first 64 bytes) ===")
addr = 7 * 0x1DA  # Preset 8 = index 7
body5 = bytes([
    0x05,
    addr & 0xFF, (addr >> 8) & 0xFF, 0x00, 0x00,
    0x40, 0x00, 0x00,  # 64 bytes
])
cs5 = (~sum(body5)) & 0xFF
raw5 = bytes([0x00, 0x59, 0x23, 0x08, 0x00, 0x00]) + body5 + bytes([cs5])
send_sysex(mo, raw5)
time.sleep(0.5)

responses = drain(mi)
for data in responses:
    print(f"  Response ({len(data)}B): {hex_str(data)}")
    if len(data) > 2 and data[0] == 0xF0 and data[-1] == 0xF7:
        inner = bytes(data[1:-1])
        # Expected decoded = 64 + 15 = 79 bytes
        decoded = decode_7bit(inner, 79)
        print(f"  Decoded (79): {hex_str(decoded)}")
        if len(decoded) >= 78:
            flash_data = decoded[14:14+64]
            print(f"  Flash data (64B): {hex_str(flash_data)}")
            # Compare with our generated preset
            import re, os
            driver_path = 'zyngine/ctrldev/zynthian_ctrldev_sinco_smk25.py'
            if os.path.exists(driver_path):
                src = open(driver_path).read()
                pre_class = src.split('class zynthian_ctrldev_sinco_smk25')[0]
                lines = [l for l in pre_class.splitlines() if not l.startswith(('import ', 'from '))]
                ns = {}
                exec('\n'.join(lines), ns)
                func_match = re.search(r'^(def _build_preset_data\(\):.*?)(?=\ndef |\nclass |\Z)', src, re.DOTALL | re.MULTILINE)
                if func_match:
                    exec(func_match.group(1), ns)
                    expected = ns['_build_preset_data']()[:64]
                    match_count = sum(1 for a, b in zip(flash_data, expected) if a == b)
                    print(f"  Match with _build_preset_data: {match_count}/64 bytes")

if not responses:
    print("  No response")

# -------------------------------------------------------
# Test 5: Try reading preset index from FlashType 4 
# -------------------------------------------------------
print("\n=== Flash Read: FlashType 4, bytes 0x0A-0x0B ===")
body6 = bytes([
    0x04,
    0x0A, 0x00, 0x00, 0x00,  # addr = 0x0A
    0x02, 0x00, 0x00,         # length = 2
])
cs6 = (~sum(body6)) & 0xFF
raw6 = bytes([0x00, 0x59, 0x23, 0x08, 0x00, 0x00]) + body6 + bytes([cs6])
send_sysex(mo, raw6)
time.sleep(0.5)

responses = drain(mi)
for data in responses:
    print(f"  Response ({len(data)}B): {hex_str(data)}")
    if len(data) > 2 and data[0] == 0xF0 and data[-1] == 0xF7:
        inner = bytes(data[1:-1])
        decoded = decode_7bit(inner, 17)  # 2 + 15 = 17
        print(f"  Decoded (17): {hex_str(decoded)}")
        if len(decoded) >= 16:
            print(f"  Preset index byte: 0x{decoded[14]:02X} = preset {decoded[14]+1}")
if not responses:
    print("  No response")

mo.close_port()
mi.close_port()
print("\nDone.")

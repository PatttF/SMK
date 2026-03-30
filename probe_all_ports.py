#!/usr/bin/env python3
"""Try listening on all ports simultaneously for any device responses."""
import rtmidi, time, sys, os
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

def encode_7bit(data):
    result = bytearray()
    acc, bits = 0, 0
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

def hex_str(data):
    return " ".join(f"{b:02X}" for b in data[:60])

# Open all input ports
inputs = {}
mi_all = rtmidi.MidiIn()
for i, name in enumerate(mi_all.get_ports()):
    if 'SINCO' in name:
        port = rtmidi.MidiIn()
        port.open_port(i)
        inputs[name] = port
        print(f"Opened IN: {name}")

# Open Private out
mo = rtmidi.MidiOut()
for i, name in enumerate(mo.get_ports()):
    if 'Private' in name:
        mo.open_port(i)
        print(f"Opened OUT: {name}")
        break

# Drain all ports
time.sleep(0.3)
for name, port in inputs.items():
    while port.get_message():
        pass

def listen_all(seconds=1.0):
    start = time.time()
    found = False
    while time.time() - start < seconds:
        for name, port in inputs.items():
            r = port.get_message()
            if r:
                data, dt = r
                print(f"  [{name}] ({len(data)}B): {hex_str(data)}")
                found = True
        time.sleep(0.005)
    return found

# Send device ID on Private, listen on all
print("\n=== Device ID query → listen all ports ===")
query = bytes([0x00, 0x59, 0x11, 0x00, 0x00, 0x00, 0xFF])
encoded = encode_7bit(query)
mo.send_message([0xF0] + list(encoded) + [0xF7])
if not listen_all(1.0):
    print("  No response on any port")

# Send flash read FlashType 4, listen all
print("\n=== Flash read FlashType 4 → listen all ports ===")
body = bytes([0x04, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00])
cs = (~sum(body)) & 0xFF
raw = bytes([0x00, 0x59, 0x23, 0x08, 0x00, 0x00]) + body + bytes([cs])
encoded = encode_7bit(raw)
mo.send_message([0xF0] + list(encoded) + [0xF7])
if not listen_all(1.0):
    print("  No response on any port")

# Send flash read FlashType 5, listen all
print("\n=== Flash read FlashType 5 (preset 8 header) → listen all ===")
addr = 7 * 0x1DA
body5 = bytes([0x05, addr & 0xFF, (addr >> 8) & 0xFF, 0x00, 0x00, 0x10, 0x00, 0x00])
cs5 = (~sum(body5)) & 0xFF
raw5 = bytes([0x00, 0x59, 0x23, 0x08, 0x00, 0x00]) + body5 + bytes([cs5])
encoded5 = encode_7bit(raw5)
mo.send_message([0xF0] + list(encoded5) + [0xF7])
if not listen_all(1.0):
    print("  No response on any port")

# Also try sending via Master out
print("\n=== Try sending queries on Master OUT ===")
mo2 = rtmidi.MidiOut()
for i, name in enumerate(mo2.get_ports()):
    if 'Master' in name:
        mo2.open_port(i)
        print(f"Opened Master OUT: {name}")
        break

# Device ID on Master
mo2.send_message([0xF0] + list(encode_7bit(bytes([0x00, 0x59, 0x11, 0x00, 0x00, 0x00, 0xFF]))) + [0xF7])
if not listen_all(1.0):
    print("  No response on any port via Master")

# Just listen for 3 seconds to see if device sends anything spontaneously
print("\n=== Passive listen for 3 seconds ===")
if not listen_all(3.0):
    print("  No spontaneous messages from device")

# Cleanup
for port in inputs.values():
    port.close_port()
mo.close_port()
mo2.close_port()
print("\nDone.")

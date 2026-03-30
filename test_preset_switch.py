#!/usr/bin/env python3
"""Isolate which method switches presets live.
Run with: python3 test_preset_switch.py <approach_number>
Switch device to preset 1 manually before each test.
"""
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

def send_sysex(mo, raw_payload):
    encoded = encode_7bit(raw_payload)
    mo.send_message([0xF0] + list(encoded) + [0xF7])
    time.sleep(0.05)

def write_flash(mo, flash_type, addr, data):
    data_len = len(data)
    size = data_len + 8
    header = bytes([0x00, 0x59, 0x22,
                    size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF])
    body = bytes([flash_type,
                  addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF,
                  data_len & 0xFF, (data_len >> 8) & 0xFF, (data_len >> 16) & 0xFF]) + bytes(data)
    cs = (~sum(body)) & 0xFF
    send_sysex(mo, header + body + bytes([cs]))

def commit_flash(mo, flash_type, addr=0):
    body = bytes([flash_type,
                  addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF,
                  0, 0, 0])
    cs = (~sum(body)) & 0xFF
    send_sysex(mo, bytes([0x00, 0x59, 0x22, 8, 0, 0]) + body + bytes([cs]))

TARGET = 7  # preset 8

priv_out = rtmidi.MidiOut()
for i, name in enumerate(priv_out.get_ports()):
    if 'Private' in name:
        priv_out.open_port(i)
        break

master_out = rtmidi.MidiOut()
for i, name in enumerate(master_out.get_ports()):
    if 'Master' in name:
        master_out.open_port(i)
        break

approach = int(sys.argv[1]) if len(sys.argv) > 1 else 0

if approach == 0:
    print("Usage: python3 test_preset_switch.py <1-7>")
    print("  1 = PC all channels on Private")
    print("  2 = PC all channels on Master")
    print("  3 = Undocumented SysEx commands")
    print("  4 = Minimal SysEx variants")
    print("  5 = FlashType 4 write + FlashType 5 commit")
    print("  6 = FT4 two-byte writes + commit")
    print("  7 = Bank Select + PC on both ports")
    sys.exit(0)

if approach == 1:
    print(f"[1] Program Change {TARGET} on ALL channels via Private...")
    for ch in range(16):
        priv_out.send_message([0xC0 | ch, TARGET])
        time.sleep(0.02)

elif approach == 2:
    print(f"[2] Program Change {TARGET} on ALL channels via Master...")
    for ch in range(16):
        master_out.send_message([0xC0 | ch, TARGET])
        time.sleep(0.02)

elif approach == 3:
    print(f"[3] Undocumented SysEx commands...")
    for cmd in [0x24, 0x25, 0x20, 0x21, 0x30, 0x31, 0x10, 0x12]:
        raw = bytes([0x00, 0x59, cmd, 0x01, 0x00, 0x00, TARGET, (~TARGET) & 0xFF])
        send_sysex(priv_out, raw)
        time.sleep(0.05)
    print(f"  Tried: 0x24, 0x25, 0x20, 0x21, 0x30, 0x31, 0x10, 0x12")

elif approach == 4:
    print(f"[4] Minimal SysEx variants...")
    for variant in [
        bytes([0x00, 0x59, TARGET]),
        bytes([0x00, 0x59, 0x22, TARGET]),
        bytes([0x59, TARGET]),
        bytes([0x00, 0x32, TARGET]),
    ]:
        send_sysex(priv_out, variant)
        time.sleep(0.05)

elif approach == 5:
    print(f"[5] FlashType 4 write preset idx + FlashType 5 commit...")
    write_flash(priv_out, 0x04, 0x0A, bytes([TARGET]))
    time.sleep(0.05)
    commit_flash(priv_out, 0x05, 0x00)

elif approach == 6:
    print(f"[6] FT4 two-byte writes at offsets 0x00-0x0A + commit...")
    for offset in [0x00, 0x02, 0x04, 0x06, 0x08, 0x0A]:
        write_flash(priv_out, 0x04, offset, bytes([TARGET, 0x00]))
        time.sleep(0.03)
    commit_flash(priv_out, 0x04, 0x00)

elif approach == 7:
    print(f"[7] Bank Select + PC on Private and Master...")
    for port, pname in [(priv_out, "Private"), (master_out, "Master")]:
        port.send_message([0xB0, 0x00, 0x00])
        port.send_message([0xB0, 0x20, 0x00])
        port.send_message([0xC0, TARGET])
        time.sleep(0.3)
        print(f"  Sent on {pname}")

time.sleep(0.3)
print("Done. Did it switch?")

priv_out.close_port()
master_out.close_port()

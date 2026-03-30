#!/usr/bin/env python3
"""Run combinations of approaches to find the minimal set that switches presets.
Usage: python3 test_preset_switch_combo.py <combo>
  all   = approaches 1-7 (confirm it still works)
  a     = approaches 1-4 (PC + SysEx)
  b     = approaches 5-7 (flash writes + bank select)
  5+6   = just flash write approaches
  6+7   = flash writes + bank select
  6only = FT4 multi-offset writes + commit (no other approaches)
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

TARGET = 7

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

combo = sys.argv[1] if len(sys.argv) > 1 else 'help'

def do_1():
    print("  [1] PC all ch on Private")
    for ch in range(16):
        priv_out.send_message([0xC0 | ch, TARGET])
        time.sleep(0.02)

def do_2():
    print("  [2] PC all ch on Master")
    for ch in range(16):
        master_out.send_message([0xC0 | ch, TARGET])
        time.sleep(0.02)

def do_3():
    print("  [3] Undocumented SysEx")
    for cmd in [0x24, 0x25, 0x20, 0x21, 0x30, 0x31, 0x10, 0x12]:
        raw = bytes([0x00, 0x59, cmd, 0x01, 0x00, 0x00, TARGET, (~TARGET) & 0xFF])
        send_sysex(priv_out, raw)

def do_4():
    print("  [4] Minimal SysEx variants")
    for variant in [
        bytes([0x00, 0x59, TARGET]),
        bytes([0x00, 0x59, 0x22, TARGET]),
        bytes([0x59, TARGET]),
        bytes([0x00, 0x32, TARGET]),
    ]:
        send_sysex(priv_out, variant)

def do_5():
    print("  [5] FT4 write @0x0A + FT5 commit")
    write_flash(priv_out, 0x04, 0x0A, bytes([TARGET]))
    time.sleep(0.05)
    commit_flash(priv_out, 0x05, 0x00)

def do_6():
    print("  [6] FT4 multi-offset writes + FT4 commit")
    for offset in [0x00, 0x02, 0x04, 0x06, 0x08, 0x0A]:
        write_flash(priv_out, 0x04, offset, bytes([TARGET, 0x00]))
        time.sleep(0.03)
    commit_flash(priv_out, 0x04, 0x00)

def do_7():
    print("  [7] Bank Select + PC on both ports")
    for port, pname in [(priv_out, "Private"), (master_out, "Master")]:
        port.send_message([0xB0, 0x00, 0x00])
        port.send_message([0xB0, 0x20, 0x00])
        port.send_message([0xC0, TARGET])
        time.sleep(0.1)

combos = {
    'all': [do_1, do_2, do_3, do_4, do_5, do_6, do_7],
    'a': [do_1, do_2, do_3, do_4],
    'b': [do_5, do_6, do_7],
    '56': [do_5, do_6],
    '67': [do_6, do_7],
    '57': [do_5, do_7],
    '5': [do_5],
    '6': [do_6],
    '7': [do_7],
    '12': [do_1, do_2],
    '34': [do_3, do_4],    '46': [do_4, do_6],
    '45': [do_4, do_5],
    '4': [do_4],    '123': [do_1, do_2, do_3],
    '456': [do_4, do_5, do_6],
    '567': [do_5, do_6, do_7],
    '1234': [do_1, do_2, do_3, do_4],
}

if combo == 'help' or combo not in combos:
    print("Usage: python3 test_preset_switch_combo.py <combo>")
    print("Combos:", ', '.join(sorted(combos.keys())))
    sys.exit(0)

print(f"Running combo '{combo}':")
for fn in combos[combo]:
    fn()
    time.sleep(0.2)

time.sleep(0.3)
print("Done. Did it switch?")

priv_out.close_port()
master_out.close_port()

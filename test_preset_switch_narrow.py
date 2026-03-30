#!/usr/bin/env python3
"""Narrow down which SysEx variant in approach 4 + approach 6 triggers preset switch.
Usage: python3 test_preset_switch_narrow.py <variant>
  4a = [0x00, 0x59, TARGET] + approach 6
  4b = [0x00, 0x59, 0x22, TARGET] + approach 6
  4c = [0x59, TARGET] + approach 6
  4d = [0x00, 0x32, TARGET] + approach 6
  6only = just approach 6 (control)
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

variant = sys.argv[1] if len(sys.argv) > 1 else 'help'

def do_6():
    print("  + FT4 multi-offset writes + commit")
    for offset in [0x00, 0x02, 0x04, 0x06, 0x08, 0x0A]:
        write_flash(priv_out, 0x04, offset, bytes([TARGET, 0x00]))
        time.sleep(0.03)
    commit_flash(priv_out, 0x04, 0x00)

sa = bytes([0x00, 0x59, TARGET])
sb = bytes([0x00, 0x59, 0x22, TARGET])
sc = bytes([0x59, TARGET])
sd = bytes([0x00, 0x32, TARGET])
pair_map = {
    'ab': [sa, sb], 'ac': [sa, sc], 'ad': [sa, sd],
    'bc': [sb, sc], 'bd': [sb, sd], 'cd': [sc, sd],
    'abc': [sa, sb, sc], 'abd': [sa, sb, sd],
    'acd': [sa, sc, sd], 'bcd': [sb, sc, sd],
    'abcd': [sa, sb, sc, sd],
}

if variant in pair_map:
    print(f"  Combo '{variant}':")
    for sx in pair_map[variant]:
        print(f"    raw: {' '.join(f'{b:02X}' for b in sx)}")
        send_sysex(priv_out, sx)
        time.sleep(0.05)  # match combo script timing
    time.sleep(0.2)  # match combo script gap before approach 6
    do_6()
elif variant == '6slow':
    print("  Approach 6 with extra delays")
    for offset in [0x00, 0x02, 0x04, 0x06, 0x08, 0x0A]:
        write_flash(priv_out, 0x04, offset, bytes([TARGET, 0x00]))
        time.sleep(0.1)  # slower than normal
    time.sleep(0.2)
    commit_flash(priv_out, 0x04, 0x00)
elif variant == '4a':
    print(f"  SysEx [0x00, 0x59, {TARGET}]")
    send_sysex(priv_out, bytes([0x00, 0x59, TARGET]))
    do_6()
elif variant == '4b':
    print(f"  SysEx [0x00, 0x59, 0x22, {TARGET}]")
    send_sysex(priv_out, bytes([0x00, 0x59, 0x22, TARGET]))
    do_6()
elif variant == '4c':
    print(f"  SysEx [0x59, {TARGET}]")
    send_sysex(priv_out, bytes([0x59, TARGET]))
    do_6()
elif variant == '4d':
    print(f"  SysEx [0x00, 0x32, {TARGET}]")
    send_sysex(priv_out, bytes([0x00, 0x32, TARGET]))
    do_6()
elif variant == '6only':
    do_6()
else:
    print("Usage: python3 test_preset_switch_narrow.py <4a|4b|4c|4d|6only>")
    print("  Pairs: ab ac ad bc bd cd")
    print("  Triples: abc abd acd bcd")
    print("  All4: abcd")
    sys.exit(0)

time.sleep(0.3)
print("Done. Did it switch?")
priv_out.close_port()

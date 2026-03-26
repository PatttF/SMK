#!/usr/bin/env python3
"""
verify_knobs.py — Read back and verify knob configuration on the SMC-PAD Pocket.

Reads all 6 bytes of the knob struct for every preset (0–7) and knob (0–7)
and prints a table showing type, CC number, and MIDI channel.  Flags any
entry that does not match the expected values set by set_knobs_relative.py.

Expected values:
  byte[0] = 0x01       (CC Relative)
  byte[1] = 70 + knob  (CC 70–77)
  byte[2] = 0x0E       (channel 15, 0-indexed)

Requires:  pip install mido python-rtmidi
"""

import sys
import time
import mido

# ── SysEx constants ──────────────────────────────────────────────────────────
HEADER = [0x00, 0x59]
FLASH_TYPE = 0x05
CMD_READ   = 0x23

PRESET_STRIDE = 0xDD3
KNOB_STRIDE   = 6
KNOB_BASE     = 0x73

NUM_PRESETS   = 8
NUM_KNOBS     = 8

EXP_TYPE      = 0x01
CC_BASE       = 70
EXP_CHANNEL   = 0x0E

READ_TIMEOUT  = 1.0

PORT_KEYWORD  = "SMC-PAD Pocket-Private"


# ── 7-bit encoding / decoding ────────────────────────────────────────────────

def encode_7bit(data: bytes) -> list[int]:
    out = []
    for i in range(0, len(data), 7):
        chunk = data[i:i + 7]
        prefix = 0
        for j, b in enumerate(chunk):
            if b & 0x80:
                prefix |= (1 << (6 - j))
        out.append(prefix)
        for b in chunk:
            out.append(b & 0x7F)
    return out


def decode_7bit(encoded: list[int]) -> bytes:
    out = []
    i = 0
    while i < len(encoded):
        prefix = encoded[i]
        i += 1
        for j in range(7):
            if i >= len(encoded):
                break
            b = encoded[i]
            if prefix & (1 << (6 - j)):
                b |= 0x80
            out.append(b)
            i += 1
    return bytes(out)


# ── Checksum ─────────────────────────────────────────────────────────────────

def checksum(payload_from_offset6: list[int]) -> int:
    return (~sum(payload_from_offset6)) & 0xFF


# ── Packet builder ───────────────────────────────────────────────────────────

def build_read_packet(flash_type: int, address: int, length: int) -> bytes:
    addr_le = list(address.to_bytes(4, 'little'))
    len_le  = list(length.to_bytes(3, 'little'))
    inner   = [flash_type] + addr_le + len_le
    cs = checksum(inner)
    raw = HEADER + [CMD_READ] + list((len(inner) + 8).to_bytes(3, 'little')) + inner + [cs]
    return bytes(raw)


def to_sysex(raw: bytes) -> list[int]:
    return encode_7bit(raw)


# ── Port helpers ─────────────────────────────────────────────────────────────

def find_ports():
    inputs  = mido.get_input_names()
    outputs = mido.get_output_names()
    inp = next((n for n in inputs  if PORT_KEYWORD in n), None)
    out = next((n for n in outputs if PORT_KEYWORD in n), None)
    if not inp or not out:
        print("Available inputs:",  inputs,  file=sys.stderr)
        print("Available outputs:", outputs, file=sys.stderr)
        raise RuntimeError(f"Could not find MIDI port containing '{PORT_KEYWORD}'")
    return inp, out


# ── Flash read ───────────────────────────────────────────────────────────────

def flash_read(inport, outport, address: int, length: int) -> bytes:
    raw_pkt = build_read_packet(FLASH_TYPE, address, length)
    encoded = to_sysex(raw_pkt)
    outport.send(mido.Message('sysex', data=encoded))

    deadline = time.monotonic() + READ_TIMEOUT
    buf: list[int] = []
    while time.monotonic() < deadline:
        for msg in inport.iter_pending():
            if msg.type == 'sysex':
                buf.extend(msg.data)
        if buf:
            break
        time.sleep(0.01)

    if not buf:
        raise TimeoutError(f"No response reading address 0x{address:04X}")

    decoded = decode_7bit(buf)
    if len(decoded) < 15 + length:
        raise ValueError(f"Response too short: {len(decoded)} bytes")
    return decoded[15:15 + length]


# ── Main ─────────────────────────────────────────────────────────────────────

def knob_address(preset: int, knob: int) -> int:
    return (preset * PRESET_STRIDE) + (knob * KNOB_STRIDE) + KNOB_BASE


def main():
    inp_name, out_name = find_ports()
    print(f"Using input:  {inp_name}")
    print(f"Using output: {out_name}")
    print()

    errors = 0
    with mido.open_input(inp_name) as inport, mido.open_output(out_name) as outport:
        for preset in range(NUM_PRESETS):
            for knob in range(NUM_KNOBS):
                addr     = knob_address(preset, knob)
                exp_cc   = CC_BASE + knob
                raw      = flash_read(inport, outport, addr, KNOB_STRIDE)

                got_type = raw[0]
                got_cc   = raw[1]
                got_ch   = raw[2]
                rest     = raw[3:]

                ok = (got_type == EXP_TYPE and got_cc == exp_cc and got_ch == EXP_CHANNEL)
                tag = "[OK]" if ok else "[MISMATCH]"
                if not ok:
                    errors += 1

                print(
                    f"Preset {preset} Knob {knob} @ 0x{addr:04X}: "
                    f"type={got_type:02x} cc={got_cc:02x} ch={got_ch:02x} "
                    f"rest={rest.hex()} {tag}"
                )

    print()
    if errors:
        print(f"WARNING: {errors} knob(s) did not match expected values.")
        sys.exit(1)
    else:
        print("All knobs verified OK.")


if __name__ == "__main__":
    main()

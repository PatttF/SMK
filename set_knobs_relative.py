#!/usr/bin/env python3
"""
set_knobs_relative.py — Set all SMC-PAD Pocket knobs to CC Relative mode.

For every preset (0–7) and every knob (0–7):
  1. Read the existing 6-byte knob struct from flash (FlashType=5).
  2. Modify byte[0] = 0x01 (CC Relative), byte[1] = 70+knob (CC 70–77),
     byte[2] = 0x0E (MIDI channel 15, 0-indexed).
  3. Write all 6 bytes back to preserve unknown fields (bytes 3–5).
Then send the flash save/commit packet.

Requires:  pip install mido python-rtmidi
Device:    SINCO SMC-PAD Pocket (connect via USB)
"""

import sys
import time
import mido

# ── SysEx constants ──────────────────────────────────────────────────────────
HEADER = [0x00, 0x59]
FLASH_TYPE = 0x05
CMD_WRITE = 0x22
CMD_READ  = 0x23

# Knob flash layout
# flash_addr = (preset * 0xDD3) + (knob * 6) + 0x73
PRESET_STRIDE  = 0xDD3
KNOB_STRIDE    = 6
KNOB_BASE      = 0x73

NUM_PRESETS    = 8
NUM_KNOBS      = 8

KNOB_TYPE      = 0x01        # CC Relative
CC_BASE        = 70          # Knob 0 → CC 70, knob 7 → CC 77
MIDI_CHANNEL   = 0x0E        # Channel 15, 0-indexed on the wire

# How long to wait for a read response (seconds)
READ_TIMEOUT   = 1.0


# ── 7-bit encoding / decoding ────────────────────────────────────────────────

def encode_7bit(data: bytes) -> list[int]:
    """Pack raw bytes into SysEx-safe 7-bit groups."""
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
    """Unpack 7-bit-grouped SysEx bytes back to raw bytes."""
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
    """Checksum = ~(sum of bytes starting at offset 6) & 0xFF."""
    return (~sum(payload_from_offset6)) & 0xFF


# ── Packet builders ──────────────────────────────────────────────────────────

def build_read_packet(flash_type: int, address: int, length: int) -> bytes:
    """Build a Flash Read (0x23) raw payload (before 7-bit encoding)."""
    addr_le  = list(address.to_bytes(4, 'little'))
    len_le   = list(length.to_bytes(3, 'little'))
    inner = [flash_type] + addr_le + len_le
    cs = checksum(inner)
    raw = HEADER + [CMD_READ] + list((len(inner) + 8).to_bytes(3, 'little')) + inner + [cs]
    return bytes(raw)


def build_write_packet(flash_type: int, address: int, data: bytes) -> bytes:
    """Build a Flash Write (0x22) raw payload (before 7-bit encoding)."""
    addr_le  = list(address.to_bytes(4, 'little'))
    len_le   = list(len(data).to_bytes(3, 'little'))
    inner = [flash_type] + addr_le + len_le + list(data)
    cs = checksum(inner)
    total_size = len(inner) + 8
    raw = HEADER + [CMD_WRITE] + list(total_size.to_bytes(3, 'little')) + inner + [cs]
    return bytes(raw)


def build_commit_packet(flash_type: int = FLASH_TYPE) -> bytes:
    """Build a Flash Save/Commit packet (write with data_len=0, addr=0)."""
    inner = [flash_type, 0, 0, 0, 0, 0, 0, 0]  # flash_type + addr(4) + len(3)
    cs = checksum(inner)
    raw = HEADER + [CMD_WRITE] + list((8).to_bytes(3, 'little')) + inner + [cs]
    return bytes(raw)


def to_sysex(raw: bytes) -> list[int]:
    """Wrap encoded payload in F0 ... F7."""
    return encode_7bit(raw)


# ── Port helpers ─────────────────────────────────────────────────────────────

PORT_KEYWORD = "SMC-PAD Pocket-Private"


def find_ports():
    """Return (input_name, output_name) for the SMC-PAD private port."""
    inputs  = mido.get_input_names()
    outputs = mido.get_output_names()
    inp = next((n for n in inputs  if PORT_KEYWORD in n), None)
    out = next((n for n in outputs if PORT_KEYWORD in n), None)
    if not inp or not out:
        print("Available inputs:",  inputs,  file=sys.stderr)
        print("Available outputs:", outputs, file=sys.stderr)
        raise RuntimeError(f"Could not find MIDI port containing '{PORT_KEYWORD}'")
    return inp, out


# ── Flash read/write helpers ─────────────────────────────────────────────────

def flash_read(inport, outport, address: int, length: int) -> bytes:
    """Send a read request and return the decoded response data."""
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
        raise TimeoutError(f"No response from device reading address 0x{address:04X}")

    decoded = decode_7bit(buf)
    # Response: 15-byte header, then data
    if len(decoded) < 15 + length:
        raise ValueError(f"Response too short: got {len(decoded)} bytes, expected {15 + length}")
    return decoded[15:15 + length]


def flash_write(outport, address: int, data: bytes):
    """Send a flash write packet."""
    raw_pkt = build_write_packet(FLASH_TYPE, address, data)
    encoded = to_sysex(raw_pkt)
    outport.send(mido.Message('sysex', data=encoded))
    time.sleep(0.02)  # brief settle between writes


def flash_commit(outport):
    """Send the save/commit packet."""
    raw_pkt = build_commit_packet()
    encoded = to_sysex(raw_pkt)
    outport.send(mido.Message('sysex', data=encoded))
    time.sleep(0.05)


# ── Main ─────────────────────────────────────────────────────────────────────

def knob_address(preset: int, knob: int) -> int:
    return (preset * PRESET_STRIDE) + (knob * KNOB_STRIDE) + KNOB_BASE


def main():
    inp_name, out_name = find_ports()
    print(f"Using input:  {inp_name}")
    print(f"Using output: {out_name}")
    print()

    with mido.open_input(inp_name) as inport, mido.open_output(out_name) as outport:
        for preset in range(NUM_PRESETS):
            for knob in range(NUM_KNOBS):
                addr = knob_address(preset, knob)
                cc   = CC_BASE + knob

                # 1. Read existing 6 bytes
                existing = flash_read(inport, outport, addr, KNOB_STRIDE)

                # 2. Modify bytes 0, 1, 2; preserve bytes 3–5
                new_data = bytearray(existing)
                new_data[0] = KNOB_TYPE       # CC Relative
                new_data[1] = cc              # CC number
                new_data[2] = MIDI_CHANNEL    # channel 15 (0-indexed)

                # 3. Write all 6 bytes back
                flash_write(outport, addr, bytes(new_data))

                print(
                    f"Preset {preset} Knob {knob}: "
                    f"type=0x{KNOB_TYPE:02X} CC={cc} ch=15 "
                    f"@ 0x{addr:04X}"
                )

        # Commit to flash
        flash_commit(outport)

    print()
    print("Done. Power-cycle the SMC-PAD to apply.")


if __name__ == "__main__":
    main()

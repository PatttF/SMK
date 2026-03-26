#!/usr/bin/env python3
"""
verify_knobs.py

Reads back the knob type byte for every knob (all 8 knobs × all 8 presets)
from the SINCO SMC-PAD Pocket's flash and reports whether each knob is set
to CC Relative (0x01) or something else.

Prerequisites:
    pip install mido python-rtmidi

Usage:
    python verify_knobs.py
"""

import time
import mido

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
SYSEX_HEADER = [0x00, 0x59]
PORT_SUBSTR   = "Private"
FLASH_TYPE    = 0x05
CMD_READ      = 0x23

KNOB_TYPE_NAMES = {
    0x00: "CC Absolute",
    0x01: "CC Relative",
    0x02: "Note",
    0x03: "Program Change",
    0x04: "Disabled/SysEx",
}

DELAY_BETWEEN_READS = 0.10   # 100 ms (read is slower than write)
RESPONSE_TIMEOUT    = 0.50   # seconds to wait for a response


# ---------------------------------------------------------------------------
# 7-bit encoding / decoding
# ---------------------------------------------------------------------------
def encode_7bit(data: bytes) -> list:
    """
    Pack 8-bit bytes into 7-bit MIDI-safe bytes.

    For every group of 7 input bytes, emit 8 output bytes:
      - First output byte holds the MSBs of the 7 input bytes
        (bit 6 = MSB of byte 0, bit 5 = MSB of byte 1, …, bit 0 = MSB of byte 6)
      - The remaining 7 output bytes are the input bytes with their MSB cleared
    """
    out = []
    for i in range(0, len(data), 7):
        chunk = data[i:i + 7]
        msb_byte = 0
        for j, b in enumerate(chunk):
            if b & 0x80:
                msb_byte |= (1 << (6 - j))
        out.append(msb_byte)
        for b in chunk:
            out.append(b & 0x7F)
    return out


def decode_7bit(data: list) -> bytes:
    """
    Unpack 7-bit MIDI-safe bytes back into 8-bit bytes.

    For every group of 8 input bytes, emit 7 output bytes:
      - First byte of the group is the MSB byte
      - Bits 6..0 of the MSB byte restore the MSBs of the following 7 bytes
    """
    out = []
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        if not chunk:
            break
        msb_byte = chunk[0]
        for j, b in enumerate(chunk[1:]):
            msb = (msb_byte >> (6 - j)) & 0x01
            out.append((msb << 7) | (b & 0x7F))
    return bytes(out)


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------
def build_flash_read_packet(flash_type: int, address: int,
                            read_len: int) -> bytes:
    """
    Build the raw (pre-7-bit-encoding) flash-read packet.

    Structure:
        Offset  Size  Field
        ------  ----  -----
        0-1     2     Header (00 59)
        2       1     Command = 0x23
        3-5     3     Size = 8  (little-endian, fixed for read request)
        6       1     FlashType
        7-10    4     Address              (little-endian)
        11-13   3     Data length          (little-endian)
        14      1     Checksum = ~(sum of bytes from offset 6) & 0xFF
    """
    size = 8

    header  = bytes(SYSEX_HEADER)
    cmd     = bytes([CMD_READ])
    size_le = bytes([size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF])
    ft      = bytes([flash_type])
    addr_le = bytes([
        address & 0xFF,
        (address >> 8)  & 0xFF,
        (address >> 16) & 0xFF,
        (address >> 24) & 0xFF,
    ])
    dlen_le = bytes([
        read_len & 0xFF,
        (read_len >> 8)  & 0xFF,
        (read_len >> 16) & 0xFF,
    ])

    payload_for_checksum = ft + addr_le + dlen_le
    checksum = (~sum(payload_for_checksum)) & 0xFF

    return header + cmd + size_le + payload_for_checksum + bytes([checksum])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def open_ports():
    """Open the first matching input and output ports."""
    out_names = mido.get_output_names()
    in_names  = mido.get_input_names()

    out_port = in_port = None
    for name in out_names:
        if PORT_SUBSTR in name:
            out_port = mido.open_output(name)
            print(f"Opened output: {name}")
            break

    for name in in_names:
        if PORT_SUBSTR in name:
            in_port = mido.open_input(name)
            print(f"Opened input:  {name}")
            break

    if out_port is None or in_port is None:
        available = {
            "outputs": out_names,
            "inputs":  in_names,
        }
        raise RuntimeError(
            f"Could not find a port containing '{PORT_SUBSTR}'.\n"
            f"Available: {available}"
        )
    return in_port, out_port


def send_sysex(port, raw_packet: bytes):
    """7-bit encode *raw_packet* and send it as a SysEx message."""
    encoded = encode_7bit(raw_packet)
    msg = mido.Message("sysex", data=encoded)
    port.send(msg)


def receive_sysex(in_port, timeout: float) -> list | None:
    """
    Wait up to *timeout* seconds for a SysEx message and return its data bytes,
    or None if nothing arrives in time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = in_port.receive(block=False)
        if msg is not None and msg.type == "sysex":
            return list(msg.data)
        time.sleep(0.005)
    return None


def main():
    in_port, out_port = open_ports()
    print()

    all_ok = True
    for preset in range(8):
        for knob in range(8):
            addr = (preset * 0xDD3) + (knob * 6) + 0x73
            pkt  = build_flash_read_packet(FLASH_TYPE, addr, 1)
            send_sysex(out_port, pkt)

            raw_response = receive_sysex(in_port, RESPONSE_TIMEOUT)
            if raw_response is None:
                print(
                    f"Preset {preset} Knob {knob} @ 0x{addr:04X}: "
                    f"[NO RESPONSE]"
                )
                all_ok = False
                time.sleep(DELAY_BETWEEN_READS)
                continue

            decoded = decode_7bit(raw_response)
            # Response layout after decode: data starts at offset 0x0F (15)
            # per the protocol spec: response_len = data_len + 0x0F
            if len(decoded) >= 0x10:
                knob_type = decoded[0x0F]
            else:
                knob_type = None

            if knob_type is None:
                status = "[DECODE ERROR]"
                all_ok = False
            elif knob_type == 0x01:
                status = "✓ CC Relative (0x01)"
            else:
                name   = KNOB_TYPE_NAMES.get(knob_type, f"Unknown (0x{knob_type:02X})")
                status = f"✗ {name} (0x{knob_type:02X})"
                all_ok = False

            print(f"Preset {preset} Knob {knob} @ 0x{addr:04X}: {status}")
            time.sleep(DELAY_BETWEEN_READS)

    print()
    if all_ok:
        print("All knobs verified as CC Relative (0x01). ✓")
    else:
        print(
            "Some knobs are NOT set to CC Relative. "
            "Re-run set_knobs_relative.py and power-cycle the device."
        )

    in_port.close()
    out_port.close()


if __name__ == "__main__":
    main()

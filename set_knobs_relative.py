#!/usr/bin/env python3
"""
set_knobs_relative.py

Sets all 8 knobs across all 8 presets on the SINCO SMC-PAD Pocket to
CC Relative mode (type byte 0x01) by writing directly to the device's
flash via SysEx.

Prerequisites:
    pip install mido python-rtmidi

Usage:
    python set_knobs_relative.py
    (then power-cycle the SMC-PAD to apply changes)
"""

import time
import mido

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
SYSEX_HEADER = [0x00, 0x59]      # raw header before 7-bit encoding
PORT_SUBSTR   = "Private"         # substring to match the correct port name
FLASH_TYPE    = 0x05
CMD_WRITE     = 0x22
CMD_SAVE      = 0x22              # save/commit also uses 0x22 with data_len=0

KNOB_TYPE_RELATIVE = 0x01        # CC Relative

DELAY_BETWEEN_WRITES = 0.05      # 50 ms


# ---------------------------------------------------------------------------
# 7-bit MIDI encoding
# ---------------------------------------------------------------------------
def encode_7bit(data: bytes) -> list:
    """
    Pack 8-bit bytes into 7-bit MIDI-safe bytes.

    For every group of 7 input bytes, emit 8 output bytes:
      - First output byte holds the MSBs of the 7 input bytes
        (bit 6 = MSB of byte 0, bit 5 = MSB of byte 1, …, bit 0 = MSB of byte 6)
      - The remaining 7 output bytes are the input bytes with their MSB cleared

    The last group may contain fewer than 7 bytes and is handled the same way.
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


# ---------------------------------------------------------------------------
# Packet builders
# ---------------------------------------------------------------------------
def build_flash_write_packet(flash_type: int, address: int,
                             data: bytes) -> bytes:
    """
    Build the raw (pre-7-bit-encoding) flash-write packet.

    Structure:
        Offset  Size  Field
        ------  ----  -----
        0-1     2     Header (00 59)
        2       1     Command = 0x22
        3-5     3     Size = data_len + 8  (little-endian)
        6       1     FlashType
        7-10    4     Address              (little-endian)
        11-13   3     Data length          (little-endian)
        14+     N     Data bytes
        Last    1     Checksum = ~(sum of bytes from offset 6 onward) & 0xFF
    """
    data_len = len(data)
    size     = data_len + 8

    header   = bytes(SYSEX_HEADER)
    cmd      = bytes([CMD_WRITE])
    size_le  = bytes([size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF])
    ft       = bytes([flash_type])
    addr_le  = bytes([
        address & 0xFF,
        (address >> 8)  & 0xFF,
        (address >> 16) & 0xFF,
        (address >> 24) & 0xFF,
    ])
    dlen_le  = bytes([data_len & 0xFF, (data_len >> 8) & 0xFF,
                      (data_len >> 16) & 0xFF])

    # checksum covers from FlashType to end of data
    payload_for_checksum = ft + addr_le + dlen_le + bytes(data)
    checksum = (~sum(payload_for_checksum)) & 0xFF

    return header + cmd + size_le + payload_for_checksum + bytes([checksum])


def build_flash_save_packet() -> bytes:
    """
    Build the raw flash save/commit packet (data_len = 0).

    Structure:
        Offset  Size  Field
        ------  ----  -----
        0-1     2     Header (00 59)
        2       1     Command = 0x22
        3-5     3     Size = 8 (fixed, little-endian)
        6       1     FlashType = 0x05
        7-10    4     Address = 0x00000000
        11-13   3     Data length = 0
        14      1     Checksum = ~(FlashType + addr_bytes) & 0xFF
    """
    flash_type = FLASH_TYPE
    address    = 0x00000000

    header  = bytes(SYSEX_HEADER)
    cmd     = bytes([CMD_SAVE])
    size    = 8
    size_le = bytes([size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF])
    ft      = bytes([flash_type])
    addr_le = bytes([
        address & 0xFF,
        (address >> 8)  & 0xFF,
        (address >> 16) & 0xFF,
        (address >> 24) & 0xFF,
    ])
    dlen_le = bytes([0x00, 0x00, 0x00])

    payload_for_checksum = ft + addr_le + dlen_le
    checksum = (~sum(payload_for_checksum)) & 0xFF

    return header + cmd + size_le + payload_for_checksum + bytes([checksum])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def open_port():
    """Open the first output port whose name contains PORT_SUBSTR."""
    names = mido.get_output_names()
    for name in names:
        if PORT_SUBSTR in name:
            port = mido.open_output(name)
            print(f"Opened port: {name}")
            return port
    raise RuntimeError(
        f"No MIDI output port containing '{PORT_SUBSTR}' found.\n"
        f"Available ports: {names}"
    )


def send_sysex(port, raw_packet: bytes):
    """7-bit encode *raw_packet* and send it as a SysEx message."""
    encoded = encode_7bit(raw_packet)
    msg = mido.Message("sysex", data=encoded)
    port.send(msg)


def main():
    port = open_port()

    for preset in range(8):
        for knob in range(8):
            addr = (preset * 0xDD3) + (knob * 6) + 0x73
            print(
                f"Setting preset {preset} knob {knob} "
                f"@ flash addr 0x{addr:04X} → 0x{KNOB_TYPE_RELATIVE:02X}"
            )
            pkt = build_flash_write_packet(
                FLASH_TYPE, addr, bytes([KNOB_TYPE_RELATIVE])
            )
            send_sysex(port, pkt)
            time.sleep(DELAY_BETWEEN_WRITES)

    print("Sending flash save/commit…")
    save_pkt = build_flash_save_packet()
    send_sysex(port, save_pkt)
    time.sleep(DELAY_BETWEEN_WRITES)

    port.close()
    print("Done. Power-cycle the SMC-PAD to apply changes.")


if __name__ == "__main__":
    main()

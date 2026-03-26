#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ****************************************************************************
# Zynthian Control Device Driver for SINCO SMC-PAD Pocket
#
# Configures all 8 knobs across all 8 presets to CC Relative mode
# (CC 70–77, MIDI channel 15) via SysEx flash writes on init, then maps
# the top-row knobs (CC 70–73) to Zynthian ZYNPOT 0–3 during play.
#
# Copyright (C) 2024 The SMK Project Contributors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ****************************************************************************

import logging
import threading
from time import sleep

from zyngine.ctrldev.zynthian_ctrldev_base import zynthian_ctrldev_base
from zyncoder.zyncore import lib_zyncore

# ---------------------------------------------------------------------------
# Knob configuration constants
# ---------------------------------------------------------------------------

KNOB_TYPE_CC_RELATIVE = 0x01  # CC Relative mode value as used by device firmware
KNOB_CC_BASE = 70              # CC 70–77 assigned to knobs 0–7
KNOB_MIDI_CHANNEL = 0x0E      # MIDI channel 15, 0-indexed wire value

# Top-row knobs (CC 70–73) are mapped to Zynthian zynpots 0–3.
# Bottom-row knobs (CC 74–77) are left to pass through.
ZYNPOT_KNOBS = {70: 0, 71: 1, 72: 2, 73: 3}

# ---------------------------------------------------------------------------
# Flash / SysEx protocol constants
# ---------------------------------------------------------------------------

FLASH_TYPE = 0x05       # FlashType identifier used in every packet
PRESET_STRIDE = 0xDD3   # Bytes between consecutive preset blocks in flash
KNOB_STRIDE = 6         # Bytes per knob struct in flash
KNOB_BASE_ADDR = 0x73   # Flash offset of knob 0, preset 0, byte 0

NUM_PRESETS = 8
NUM_KNOBS = 8

# Safe default for the three unknown bytes (+3, +4, +5) in each knob struct.
# Byte +5 = 0x7F gives a maximum (127) range, which is a safe default.
KNOB_UNKNOWN_DEFAULTS = [0x00, 0x00, 0x7F]


# ---------------------------------------------------------------------------
# Driver class
# ---------------------------------------------------------------------------

class zynthian_ctrldev_sinco_smc_pad_pocket(zynthian_ctrldev_base):
    """Zynthian control device driver for the SINCO SMC-PAD Pocket.

    On init: configures all knobs to CC Relative mode via SysEx flash writes
             (runs in a background thread so Zynthian startup is not blocked).
    On midi_event: maps top-row knob CCs (70–73, ch 15) to ZYNPOT 0–3.
    """

    # Zynthian device-matching metadata
    # TODO: verify the exact port name shown by your system; run
    #       set_knobs_relative.py with mido to confirm, then update this list.
    dev_ids = ["SINCO SMC-PAD Pocket IN 1"]
    driver_name = "SINCO SMC-PAD Pocket"
    driver_description = (
        "SMC-PAD Pocket: configures knobs as CC Relative zynpots on init"
    )

    # Allow pad notes (ch 10) to continue routing to chains; only the
    # ch-15 knob CCs are intercepted.
    unroute_from_chains = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, state_manager, idev_in, idev_out=None):
        super().__init__(state_manager, idev_in, idev_out)
        self._config_thread = None

    def init(self):
        """Start the knob-configuration background thread, then call super."""
        self._config_thread = threading.Thread(
            target=self._configure_all_knobs,
            name="smc-pad-knob-config",
            daemon=True,
        )
        self._config_thread.start()
        super().init()

    def end(self):
        """Clean up and call super."""
        # The config thread is daemonic and will stop automatically, but we
        # join briefly so that an orderly shutdown doesn't leave writes
        # mid-flight.
        if self._config_thread and self._config_thread.is_alive():
            self._config_thread.join(timeout=5.0)
        super().end()

    # ------------------------------------------------------------------
    # MIDI event handler
    # ------------------------------------------------------------------

    def midi_event(self, ev):
        """Map top-row knob CCs to ZYNPOT; pass everything else through.

        Returns True (consume) for CC 70–73 on channel 15.
        Returns False (pass through) for all other events.
        """
        evtype = (ev[0] >> 4) & 0x0F
        ev_chan = ev[0] & 0x0F

        if evtype != 0xB or ev_chan != KNOB_MIDI_CHANNEL:
            return False

        cc_num = ev[1]
        cc_val = ev[2]

        zynpot_index = ZYNPOT_KNOBS.get(cc_num)
        if zynpot_index is None:
            return False  # Bottom-row knobs (CC 74–77) — pass through

        # Relative encoding: values < 64 → CCW (−1), > 64 → CW (+1), 64 → no change
        delta = -1 if cc_val < 64 else 1 if cc_val > 64 else 0
        if delta != 0:
            self.state_manager.send_cuia("ZYNPOT", [zynpot_index, delta])

        return True  # Consume the event

    # ------------------------------------------------------------------
    # Knob configuration (background thread)
    # ------------------------------------------------------------------

    def _configure_all_knobs(self):
        """Write CC Relative mode + CC number + channel to all 64 knobs.

        Runs in a background thread.  A short sleep at the start lets the
        device settle after the driver loads before any SysEx is sent.
        """
        sleep(0.5)
        logging.info("SMC-PAD Pocket: starting knob flash configuration …")

        for preset in range(NUM_PRESETS):
            for knob in range(NUM_KNOBS):
                cc_num = KNOB_CC_BASE + knob
                addr = (preset * PRESET_STRIDE) + (knob * KNOB_STRIDE) + KNOB_BASE_ADDR
                data = bytes(
                    [KNOB_TYPE_CC_RELATIVE, cc_num, KNOB_MIDI_CHANNEL]
                    + KNOB_UNKNOWN_DEFAULTS
                )
                self._write_flash(addr, data)
                sleep(0.02)  # brief inter-packet gap

        # Commit / save to persistent storage
        self._commit_flash()
        logging.warning(
            "SMC-PAD Pocket: Flash configured. "
            "Power-cycle the device to apply changes."
        )

    # ------------------------------------------------------------------
    # SysEx helpers
    # ------------------------------------------------------------------

    def _send_sysex(self, raw_payload):
        """7-bit encode raw_payload and send it as a SysEx message."""
        encoded = _encode_7bit(raw_payload)
        msg = bytes([0xF0]) + encoded + bytes([0xF7])
        lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))
        sleep(0.05)

    def _write_flash(self, addr, data):
        """Send a flash-write SysEx packet for *data* at *addr*."""
        raw = _build_write_packet(addr, data)
        self._send_sysex(raw)

    def _commit_flash(self):
        """Send the flash save/commit SysEx packet."""
        raw = _build_commit_packet()
        self._send_sysex(raw)


# ---------------------------------------------------------------------------
# Pure-function protocol helpers (no instance state needed)
# ---------------------------------------------------------------------------

def _encode_7bit(data):
    """Pack *data* bytes into 7-bit SysEx-safe encoding.

    For every group of up to 7 input bytes the output is 8 bytes:
      - byte 0: MSBs of the group (bit 6 = MSB of input[0], …, bit 0 = MSB of input[6])
      - bytes 1–7: input bytes each ANDed with 0x7F
    """
    result = bytearray()
    for i in range(0, len(data), 7):
        chunk = data[i : i + 7]
        msb_byte = 0
        for j, b in enumerate(chunk):
            if b & 0x80:
                msb_byte |= 1 << (6 - j)
        result.append(msb_byte)
        for b in chunk:
            result.append(b & 0x7F)
    return bytes(result)


def _decode_7bit(encoded):
    """Reverse of _encode_7bit.  Input must be a multiple of 8 bytes."""
    result = bytearray()
    for i in range(0, len(encoded), 8):
        msb_byte = encoded[i]
        for j in range(7):
            if i + 1 + j >= len(encoded):
                break
            b = encoded[i + 1 + j]
            if msb_byte & (1 << (6 - j)):
                b |= 0x80
            result.append(b)
    return bytes(result)


def _checksum(raw_from_offset_6):
    """Compute packet checksum: ~(sum of bytes) & 0xFF."""
    return (~sum(raw_from_offset_6)) & 0xFF


def _build_write_packet(addr, data):
    """Build a raw (pre-7-bit-encoding) flash-write packet.

    Packet layout (all LE, 3-byte size/length fields):
      [0x00, 0x59, 0x22, size_lo, size_mid, size_hi,
       FlashType, addr×4_LE, data_len×3_LE, *data, checksum]

    size = data_len + 8; checksum covers bytes from offset 6 onward
    (excluding the checksum byte itself).
    """
    data_len = len(data)
    size = data_len + 8

    header = bytes([
        0x00, 0x59, 0x22,
        size & 0xFF, (size >> 8) & 0xFF, (size >> 16) & 0xFF,
    ])
    body = bytes([
        FLASH_TYPE,
        addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF,
        data_len & 0xFF, (data_len >> 8) & 0xFF, (data_len >> 16) & 0xFF,
    ]) + bytes(data)

    cs = _checksum(body)
    return header + body + bytes([cs])


def _build_commit_packet():
    """Build the flash save/commit packet (write with data_len=0, addr=0, size=8)."""
    body = bytes([FLASH_TYPE, 0, 0, 0, 0, 0, 0, 0])
    cs = _checksum(body)
    return bytes([0x00, 0x59, 0x22, 8, 0, 0]) + body + bytes([cs])

#!/usr/bin/env python3
"""
Local test suite for the SINCO SMK25 SysEx protocol.

Tests run against the actual device (must be plugged in via USB).
Covers: 7-bit encoding, packet building, preset data construction,
        SysEx write/commit to device flash, and pad LED control.

Usage:
    python3 test_device.py          # Run all tests
    python3 test_device.py -v       # Verbose output
    python3 test_device.py -k led   # Run only LED tests
"""

import sys
import time
import struct
import unittest

# ---------------------------------------------------------------------------
# Extract driver constants and pure functions without importing Zynthian deps
# ---------------------------------------------------------------------------

import re

DRIVER_PATH = 'zyngine/ctrldev/zynthian_ctrldev_sinco_smk25.py'

def _load_driver_functions():
    """Load module-level constants and standalone functions from the driver."""
    src = open(DRIVER_PATH).read()

    # Everything before the class definition = constants + helpers
    pre_class = src.split('class zynthian_ctrldev_sinco_smk25')[0]
    lines = [l for l in pre_class.splitlines()
             if not l.startswith(('import ', 'from '))]
    constants_code = '\n'.join(lines)

    # Extract each standalone function (def at column 0)
    func_pattern = re.compile(r'^(def \w+\(.*?\):.*?)(?=\ndef |\nclass |\Z)',
                              re.DOTALL | re.MULTILINE)
    funcs_code = '\n\n'.join(m.group(1) for m in func_pattern.finditer(src))

    ns = {}
    exec(constants_code, ns)
    exec(funcs_code, ns)
    return ns

NS = _load_driver_functions()

# Pull out the things we need
_encode_7bit       = NS['_encode_7bit']
_build_write_packet = NS['_build_write_packet']
_build_commit_packet = NS['_build_commit_packet']
_build_ft4_write_packet = NS['_build_ft4_write_packet']
_build_ft4_commit_packet = NS['_build_ft4_commit_packet']
_build_preset_data  = NS['_build_preset_data']
FLASH_TYPE          = NS['FLASH_TYPE']
FLASH_TYPE_4        = NS['FLASH_TYPE_4']
PRESET_STRIDE       = NS['PRESET_STRIDE']
DEFAULT_PRESET      = NS['DEFAULT_PRESET']
FLASH_BASE          = NS['FLASH_BASE']
PAD_STRIDE          = NS['PAD_STRIDE']
RGB_OFFSET          = NS['RGB_OFFSET']
BANK1_OFFSET        = NS['BANK1_OFFSET']
BANK2_OFFSET        = NS['BANK2_OFFSET']

# ---------------------------------------------------------------------------
# MIDI port helpers
# ---------------------------------------------------------------------------

try:
    import rtmidi
    HAS_RTMIDI = True
except ImportError:
    HAS_RTMIDI = False

PRIVATE_PORT_NAME = 'SINCO SMK25-Private'
MASTER_PORT_NAME  = 'SINCO SMK25-Master'

def find_out_port(name):
    mo = rtmidi.MidiOut()
    for i, p in enumerate(mo.get_ports()):
        if name in p:
            mo.open_port(i)
            return mo
    return None

def find_in_port(name):
    mi = rtmidi.MidiIn()
    for i, p in enumerate(mi.get_ports()):
        if name in p:
            mi.open_port(i)
            return mi
    return None

def send_sysex(port, raw_payload):
    """7-bit encode and frame as SysEx, then send."""
    encoded = _encode_7bit(raw_payload)
    msg = [0xF0] + list(encoded) + [0xF7]
    port.send_message(msg)

def write_flash(port, addr, data):
    raw = _build_write_packet(addr, data)
    send_sysex(port, raw)

def commit_flash(port, addr=0):
    raw = _build_commit_packet(addr)
    send_sysex(port, raw)


# ===========================================================================
# Unit tests — pure functions (no device needed)
# ===========================================================================

class Test7BitEncoding(unittest.TestCase):
    """Test the 7-bit SysEx encoding algorithm."""

    def test_empty(self):
        self.assertEqual(_encode_7bit(b''), b'')

    def test_single_byte(self):
        # 0xFF → bits: 11111111 → first 7 bits = 1111111 (0x7F), remaining 1 bit = 1 (0x01)
        result = _encode_7bit(b'\xFF')
        self.assertEqual(result, bytes([0x7F, 0x01]))

    def test_zero_byte(self):
        result = _encode_7bit(b'\x00')
        self.assertEqual(result, bytes([0x00, 0x00]))

    def test_all_7bit_safe(self):
        """All output bytes must be ≤ 0x7F (SysEx requirement)."""
        test_data = bytes(range(256))
        encoded = _encode_7bit(test_data)
        for i, b in enumerate(encoded):
            self.assertLessEqual(b, 0x7F,
                f"Byte {i} of encoded output is 0x{b:02X} (> 0x7F)")

    def test_known_pattern(self):
        # 0x00, 0x59 → first 7 bits of 0x00 = 0x00, then 1 bit of 0x00 + 6 bits of 0x59...
        result = _encode_7bit(bytes([0x00, 0x59]))
        # Verify round-trip by decoding
        decoded = _decode_7bit(result, 2)
        self.assertEqual(decoded, bytes([0x00, 0x59]))

    def test_roundtrip(self):
        """Encode then decode should return original data."""
        for length in [1, 2, 7, 8, 64, 474]:
            data = bytes([i & 0xFF for i in range(length)])
            encoded = _encode_7bit(data)
            decoded = _decode_7bit(encoded, length)
            self.assertEqual(decoded, data, f"Round-trip failed for length {length}")


def _decode_7bit(encoded, expected_len):
    """Decode 7-bit encoded SysEx data back to raw bytes."""
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


class TestPacketBuilding(unittest.TestCase):
    """Test SysEx packet construction."""

    def test_write_packet_structure(self):
        pkt = _build_write_packet(0x0CF6, b'\x01\x02\x03')
        # Header
        self.assertEqual(pkt[0], 0x00)  # Manufacturer ID 1
        self.assertEqual(pkt[1], 0x59)  # Manufacturer ID 2
        self.assertEqual(pkt[2], 0x22)  # Write command
        # Size = data_len(3) + 8 = 11
        self.assertEqual(pkt[3], 11)
        self.assertEqual(pkt[4], 0)
        self.assertEqual(pkt[5], 0)
        # FlashType
        self.assertEqual(pkt[6], FLASH_TYPE)
        # Address (LE)
        self.assertEqual(pkt[7], 0xF6)   # 0x0CF6 & 0xFF
        self.assertEqual(pkt[8], 0x0C)   # (0x0CF6 >> 8) & 0xFF
        # Data length (LE)
        self.assertEqual(pkt[11], 3)
        self.assertEqual(pkt[12], 0)
        # Data
        self.assertEqual(pkt[14:17], b'\x01\x02\x03')
        # Checksum
        body = pkt[6:-1]
        expected_cs = (~sum(body)) & 0xFF
        self.assertEqual(pkt[-1], expected_cs)

    def test_commit_packet(self):
        pkt = _build_commit_packet(0x0CF6)
        self.assertEqual(pkt[2], 0x22)
        self.assertEqual(pkt[3], 8)       # size = 8 for commit
        # data_len should be 0
        self.assertEqual(pkt[11], 0)
        self.assertEqual(pkt[12], 0)
        self.assertEqual(pkt[13], 0)
        # Checksum
        body = pkt[6:-1]
        expected_cs = (~sum(body)) & 0xFF
        self.assertEqual(pkt[-1], expected_cs)

    def test_write_64_byte_chunk(self):
        """Verify a 64-byte chunk packet has correct size field."""
        data = bytes(range(64))
        pkt = _build_write_packet(0, data)
        size = pkt[3] | (pkt[4] << 8) | (pkt[5] << 16)
        self.assertEqual(size, 64 + 8)

    def test_checksum_ones_complement(self):
        """Verify checksum is one's complement of body sum."""
        data = bytes([0xFF] * 10)
        pkt = _build_write_packet(0x100, data)
        body = pkt[6:-1]
        self.assertEqual((sum(body) + pkt[-1]) & 0xFF, 0xFF,
            "sum(body) + checksum should equal 0xFF (one's complement)")

    def test_ft4_write_packet(self):
        """Verify FlashType 4 write packet structure."""
        pkt = _build_ft4_write_packet(0x0A, bytes([7, 0]))
        self.assertEqual(pkt[2], 0x22)
        self.assertEqual(pkt[6], FLASH_TYPE_4)
        self.assertEqual(pkt[7], 0x0A)  # addr low byte
        body = pkt[6:-1]
        expected_cs = (~sum(body)) & 0xFF
        self.assertEqual(pkt[-1], expected_cs)

    def test_ft4_commit_packet(self):
        """Verify FlashType 4 commit packet structure."""
        pkt = _build_ft4_commit_packet()
        self.assertEqual(pkt[6], FLASH_TYPE_4)
        self.assertEqual(pkt[11], 0)  # data_len = 0
        body = pkt[6:-1]
        expected_cs = (~sum(body)) & 0xFF
        self.assertEqual(pkt[-1], expected_cs)


class TestPresetData(unittest.TestCase):
    """Test the preset data builder."""

    def test_preset_length(self):
        preset = _build_preset_data()
        self.assertEqual(len(preset), PRESET_STRIDE,
            f"Preset should be {PRESET_STRIDE} bytes, got {len(preset)}")

    def test_pitch_bend(self):
        preset = _build_preset_data()
        self.assertEqual(preset[0x04], 0x7F, "Pitch bend range should be 127")

    def test_keyboard_chromatic(self):
        preset = _build_preset_data()
        for i in range(25):
            self.assertEqual(preset[0x05 + i], i,
                f"Key {i} should map to note offset {i}")

    def test_transport_buttons(self):
        preset = _build_preset_data()
        expected = [(102, 1), (103, 1), (104, 1)]
        for idx, (cc, val) in enumerate(expected):
            base = 0x01E + idx * 0x46
            self.assertEqual(preset[base + 2], cc, f"Button {idx} CC")
            self.assertEqual(preset[base + 3], val, f"Button {idx} value")

    def test_knob_page1_count(self):
        preset = _build_preset_data()
        # 8 knobs × 6 bytes = 48 bytes from 0x0F0 to 0x120
        non_zero = sum(1 for b in preset[0x0F0:0x120] if b != 0)
        self.assertGreater(non_zero, 0, "Knob page 1 should have data")

    def test_knob_page1_types(self):
        preset = _build_preset_data()
        for i in range(8):
            off = 0x0F0 + i * 6
            self.assertEqual(preset[off], 0x03,
                f"Knob {i+1} page 1 should be CW encoder (type=0x03)")

    def test_knob_page1_ccs(self):
        preset = _build_preset_data()
        expected_ccs = [20, 21, 22, 23, 24, 25, 26, 27]
        for i, cc in enumerate(expected_ccs):
            off = 0x0F0 + i * 6 + 3  # CC at offset +3
            self.assertEqual(preset[off], cc,
                f"Knob {i+1} CC should be {cc}, got {preset[off]}")

    def test_knob_page2_has_admin(self):
        preset = _build_preset_data()
        # First knob on page 2 should be CC 28 (Admin/Menu)
        self.assertEqual(preset[0x120 + 3], 28)

    def test_pad_bank1_structure(self):
        preset = _build_preset_data()
        expected_ccs = [105, 106, 107, 112, 89, 90, 91, 96]
        for i, cc in enumerate(expected_ccs):
            off = 0x150 + i * 8
            self.assertEqual(preset[off], 0x02, f"Pad {i} type should be 0x02")
            self.assertEqual(preset[off + 1], 0x09, f"Pad {i} sub should be 0x09")
            self.assertEqual(preset[off + 2], cc, f"Pad {i} CC should be {cc}")
            self.assertEqual(preset[off + 4], 0x7F, f"Pad {i} velocity should be 127")

    def test_pad_bank2_structure(self):
        preset = _build_preset_data()
        expected_ccs = [108, 109, 110, 111, 92, 93, 94, 95]
        for i, cc in enumerate(expected_ccs):
            off = 0x190 + i * 8
            self.assertEqual(preset[off + 2], cc, f"Bank2 pad {i} CC should be {cc}")

    def test_tail_settings(self):
        preset = _build_preset_data()
        self.assertEqual(preset[0x1D2], 0x01, "Velocity curve")
        self.assertEqual(preset[0x1D4], 0x7F, "Max velocity")
        self.assertEqual(preset[0x1D7], 0x40, "Aftertouch sensitivity")
        self.assertEqual(preset[0x1D9], 0x7F, "Pitch bend range (tail)")

    def test_matches_mkc_file(self):
        """Verify generated preset matches the reference .mkc file
        (excluding initial pad RGB which the driver sets dynamically)."""
        try:
            mkc = open('Loadtopreset8inmidisuite.mkc', 'rb').read()
        except FileNotFoundError:
            self.skipTest(".mkc file not found")

        preset = _build_preset_data()
        self.assertEqual(len(preset), len(mkc), "Preset length mismatch")

        # Compare everything except pad RGB bytes (offsets +5,+6,+7 in each 8-byte pad)
        diffs = []
        for i in range(len(preset)):
            if preset[i] != mkc[i]:
                # Check if this is a pad RGB byte (acceptable difference)
                in_bank1 = 0x150 <= i < 0x190
                in_bank2 = 0x190 <= i < 0x1D0
                if in_bank1:
                    pad_off = (i - 0x150) % 8
                elif in_bank2:
                    pad_off = (i - 0x190) % 8
                else:
                    pad_off = -1

                if pad_off in (5, 6, 7):
                    continue  # Pad RGB - acceptable
                diffs.append((i, preset[i], mkc[i]))

        self.assertEqual(diffs, [],
            f"Non-RGB differences from .mkc: {[(f'0x{a:04X}', f'gen=0x{g:02X}', f'mkc=0x{m:02X}') for a,g,m in diffs]}")


# ===========================================================================
# Device tests — require SMK25 plugged in via USB
# ===========================================================================

@unittest.skipUnless(HAS_RTMIDI, "python-rtmidi not installed")
class TestDevicePorts(unittest.TestCase):
    """Verify device MIDI ports are accessible."""

    def test_private_port_exists(self):
        mo = rtmidi.MidiOut()
        ports = mo.get_ports()
        matches = [p for p in ports if 'Private' in p]
        self.assertTrue(matches, f"No Private port found. Available: {ports}")

    def test_master_port_exists(self):
        mi = rtmidi.MidiIn()
        ports = mi.get_ports()
        matches = [p for p in ports if 'Master' in p]
        self.assertTrue(matches, f"No Master port found. Available: {ports}")

    def test_three_ports(self):
        mo = rtmidi.MidiOut()
        ports = [p for p in mo.get_ports() if 'SINCO' in p]
        self.assertEqual(len(ports), 3, f"Expected 3 SINCO ports, got: {ports}")


@unittest.skipUnless(HAS_RTMIDI, "python-rtmidi not installed")
class TestDeviceSysEx(unittest.TestCase):
    """Send SysEx to the actual device and verify it doesn't reject/crash."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_out_port(PRIVATE_PORT_NAME)
        if cls.port is None:
            raise unittest.SkipTest(f"Cannot open {PRIVATE_PORT_NAME}")

    @classmethod
    def tearDownClass(cls):
        if cls.port:
            cls.port.close_port()

    def test_write_single_byte(self):
        """Write a single byte to pad 0 bank 1 RGB (should change LED)."""
        addr = FLASH_BASE + BANK1_OFFSET + 0 * PAD_STRIDE + RGB_OFFSET
        write_flash(self.port, addr, bytes([0, 40, 40]))  # dim cyan
        time.sleep(0.03)
        # No crash = pass (we can't read back, but device accepts it)

    def test_write_and_commit(self):
        """Write + commit cycle to pad 0 — LED should visibly change."""
        addr = FLASH_BASE + BANK1_OFFSET + 0 * PAD_STRIDE + RGB_OFFSET
        write_flash(self.port, addr, bytes([0, 40, 40]))
        time.sleep(0.03)
        commit_flash(self.port, FLASH_BASE)
        time.sleep(0.05)
        # Success if no crash


@unittest.skipUnless(HAS_RTMIDI, "python-rtmidi not installed")
class TestDevicePresetWrite(unittest.TestCase):
    """Write the full preset to device flash and verify no errors."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_out_port(PRIVATE_PORT_NAME)
        if cls.port is None:
            raise unittest.SkipTest(f"Cannot open {PRIVATE_PORT_NAME}")

    @classmethod
    def tearDownClass(cls):
        if cls.port:
            cls.port.close_port()

    def test_write_full_preset(self):
        """Write all 474 bytes of preset 8 in 64-byte chunks + commit."""
        preset_data = _build_preset_data()
        flash_addr = DEFAULT_PRESET * PRESET_STRIDE  # 0x0CF6

        chunk_size = 64
        for offset in range(0, len(preset_data), chunk_size):
            chunk = preset_data[offset:offset + chunk_size]
            write_flash(self.port, flash_addr + offset, chunk)
            time.sleep(0.03)

        commit_flash(self.port, flash_addr)
        time.sleep(0.1)
        # If we get here without exception, the device accepted all packets


@unittest.skipUnless(HAS_RTMIDI, "python-rtmidi not installed")
class TestDevicePadLEDs(unittest.TestCase):
    """Test pad LED color control on the live device."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_out_port(PRIVATE_PORT_NAME)
        if cls.port is None:
            raise unittest.SkipTest(f"Cannot open {PRIVATE_PORT_NAME}")

    @classmethod
    def tearDownClass(cls):
        if cls.port:
            cls.port.close_port()

    def _set_pad_rgb(self, bank_offset, pad_idx, r, g, b):
        addr = FLASH_BASE + bank_offset + pad_idx * PAD_STRIDE + RGB_OFFSET
        write_flash(self.port, addr, bytes([r, g, b]))
        time.sleep(0.02)

    def _commit(self):
        commit_flash(self.port, FLASH_BASE)
        time.sleep(0.05)

    def test_all_pads_red(self):
        """Set all 16 pads to red, commit, then restore."""
        for bank_off in [BANK1_OFFSET, BANK2_OFFSET]:
            for i in range(8):
                self._set_pad_rgb(bank_off, i, 255, 0, 0)

        # Write pad 0 bank 1 last (trigger refresh)
        self._set_pad_rgb(BANK1_OFFSET, 0, 255, 0, 0)
        self._commit()
        time.sleep(0.5)

        # Restore to dim solo/mute colors
        solo_off = (0, 40, 40)
        mute_off = (40, 0, 40)
        for bank_off in [BANK1_OFFSET, BANK2_OFFSET]:
            for i in range(4):  # top row = solo
                self._set_pad_rgb(bank_off, i, *solo_off)
            for i in range(4, 8):  # bottom row = mute
                self._set_pad_rgb(bank_off, i, *mute_off)

        self._set_pad_rgb(BANK1_OFFSET, 0, *solo_off)
        self._commit()

    def test_single_pad_green(self):
        """Set pad 0 bank 1 to bright green and back."""
        self._set_pad_rgb(BANK1_OFFSET, 0, 0, 255, 0)
        self._commit()
        time.sleep(0.3)
        self._set_pad_rgb(BANK1_OFFSET, 0, 0, 40, 40)
        self._commit()

    def test_pad0_last_triggers_refresh(self):
        """Verify that writing pad 0 last is needed for LED refresh.
        Write pad 7 to blue, then pad 0 to unchanged, then commit."""
        # Set pad 7 to blue
        self._set_pad_rgb(BANK1_OFFSET, 7, 0, 0, 255)
        time.sleep(0.02)
        # Touch pad 0 (unchanged color) to trigger refresh
        self._set_pad_rgb(BANK1_OFFSET, 0, 0, 40, 40)
        self._commit()
        time.sleep(0.3)
        # Restore pad 7
        self._set_pad_rgb(BANK1_OFFSET, 7, 40, 0, 40)
        self._set_pad_rgb(BANK1_OFFSET, 0, 0, 40, 40)
        self._commit()


@unittest.skipUnless(HAS_RTMIDI, "python-rtmidi not installed")
class TestDeviceMidiInput(unittest.TestCase):
    """Listen for MIDI input from the device (requires user interaction)."""

    @classmethod
    def setUpClass(cls):
        cls.port = find_in_port(MASTER_PORT_NAME)
        if cls.port is None:
            raise unittest.SkipTest(f"Cannot open {MASTER_PORT_NAME}")

    @classmethod
    def tearDownClass(cls):
        if cls.port:
            cls.port.close_port()

    def test_port_opens(self):
        """Master input port should open without error."""
        self.assertIsNotNone(self.port)

    def test_flush_buffer(self):
        """Read and discard any pending messages."""
        count = 0
        while True:
            msg = self.port.get_message()
            if msg is None:
                break
            count += 1
        # Just verifying we can read without crash


if __name__ == '__main__':
    print(f"SINCO SMK25 Test Suite")
    print(f"Driver: {DRIVER_PATH}")
    print(f"Preset size: {PRESET_STRIDE} bytes")
    print(f"Target preset: {DEFAULT_PRESET + 1} (flash addr 0x{DEFAULT_PRESET * PRESET_STRIDE:04X})")
    print()
    unittest.main(verbosity=2)

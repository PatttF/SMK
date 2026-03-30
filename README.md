# SMK25 — Complete Protocol Reference & Zynthian Driver

A reverse-engineered protocol guide for the SINCO(MVAVE) SMK25 MIDI controller,
plus a Zynthian control device driver that auto-configures the device on
startup via SysEx — **no MidiSuite desktop app required**.

> **Hardware tested**: SINCO (MVAVE) SMK25 (USB VID `0x4353`, PID `0x4B4D`, Version 1.00)

---

## Table of Contents

- [Quick Start](#quick-start)
- [USB MIDI Ports](#usb-midi-ports)
- [Controller Mapping](#controller-mapping)
- [SysEx Protocol](#sysex-protocol)
  - [7-Bit Encoding](#7-bit-encoding)
  - [Flash Types](#flash-types)
  - [Write Command (0x22)](#write-command-0x22)
  - [Commit / Save Command](#commit--save-command)
  - [Read Command (0x23)](#read-command-0x23)
  - [Chunked Writes](#chunked-writes)
  - [Checksum Algorithm](#checksum-algorithm)
- [Flash Preset Layout](#flash-preset-layout)
  - [FlashType 4 — Device Header](#flashtype-4--device-header)
  - [FlashType 5 — Preset Storage](#flashtype-5--preset-storage)
  - [Single Preset Layout (474 bytes)](#single-preset-layout-474-bytes)
  - [Global Header](#global-header)
  - [Keyboard Note Offsets](#keyboard-note-offsets)
  - [Transport Button Entries](#transport-button-entries)
  - [Knob Entries](#knob-entries)
  - [Pad Entries](#pad-entries)
  - [Tail Settings](#tail-settings)
- [Pad LED Control](#pad-led-control)
  - [LED Update Protocol](#led-update-protocol)
  - [Pad 0 Refresh Trigger](#pad-0-refresh-trigger)
  - [Full LED Update Cycle](#full-led-update-cycle)
  - [Single-Pad Fast Update](#single-pad-fast-update)
  - [Address Calculation](#address-calculation)
- [Preset Switching](#preset-switching)
- [.mkc File Format](#mkc-file-format)
- [Protocol Limitations](#protocol-limitations)
- [Bluetooth LE (BLE) Support](#bluetooth-le-ble-support)
- [Driver Architecture](#driver-architecture)
- [Testing](#testing)
- [SMK25 vs SMC-PAD Differences](#smk25-vs-smc-pad-differences)
- [References](#references)

---

## Quick Start

**USB:**

1. Copy `zyngine/ctrldev/zynthian_ctrldev_sinco_smk25.py` to your Zynthian's
   `/zynthian/zynthian-ui/zyngine/ctrldev/` directory.
2. Connect the SMK25 via USB.
3. In the Zynthian webconf UI, enable the "SINCO SMK25" control device.
4. The driver auto-programs preset 8, switches to it, and sets pad LEDs on
   every startup — no MidiSuite needed.

**Bluetooth LE:**

1. Copy `zyngine/ctrldev/zynthian_ctrldev_sinco_smk25_bt.py` to the same directory.
2. Pair the SMK25 via Bluetooth (device name `SMK25V2`).
3. Enable the "SINCO SMK25 Bluetooth" control device.
4. Same auto-configuration — preset write + switch + LEDs over BLE GATT.

---

## Controller Mapping

### Knobs (8 encoders, 2 pages)

**Page 1** — primary controls:

| Knob | CC  | Function           | Type       | Range | Speed  |
|------|-----|--------------------|------------|-------|--------|
| 1    | 20  | ZYNPOT 0 (screen)  | CW encoder | 0–1   | Normal |
| 2    | 21  | ZYNPOT 1 (screen)  | CW encoder | 0–1   | Normal |
| 3    | 22  | ZYNPOT 2 (screen)  | CW encoder | 0–1   | Normal |
| 4    | 23  | ZYNPOT 3 (screen)  | CW encoder | 0–1   | Normal |
| 5    | 24  | Arrow Left / Right | CW encoder | 0–1   | Free   |
| 6    | 25  | Arrow Up / Down    | CW encoder | 0–1   | Free   |
| 7    | 26  | Preset prev / next | CW encoder | 0–1   | Free   |
| 8    | 27  | BACK / SELECT      | CW encoder | 0–1   | Free   |

**Page 2** — duplicated navigation + extra CCs:

| Knob | CC  | Function           | Type       | Range | Speed  |
|------|-----|--------------------|------------|-------|--------|
| 9    | 28  | Admin / Menu       | CW encoder | 0–1   | Slow   |
| 10   | 29  | CC pass-through    | CC-Standard| 0–127 | Normal |
| 11   | 30  | CC pass-through    | CC-Standard| 0–127 | Normal |
| 12   | 27  | BACK / SELECT (dup)| CW encoder | 0–1   | Normal |
| 13   | 28  | Admin / Menu (dup) | CW encoder | 0–1   | Free   |
| 14   | 25  | Arrow U/D (dup)    | CW encoder | 0–1   | Free   |
| 15   | 46  | CC pass-through    | CC-Standard| 0–127 | Free   |
| 16   | 27  | BACK / SELECT (dup)| CW encoder | 0–1   | Free   |

All CW-encoder knobs send only CC value 0 (CCW) or 1 (CW), giving ±1 delta
behavior. The duplicated navigation knobs on page 2 let you navigate
admin/options menus without switching back to page 1.

All knobs transmit on MIDI channel 1 (wire channel 0).

### Transport Buttons (CC Single, Channel 1, Value 1)

| Button | CC  | Function       |
|--------|-----|----------------|
| PLAY   | 102 | Toggle Play    |
| STOP   | 103 | Stop           |
| REC    | 104 | Toggle Record  |

### Pads (CC Toggle, Channel 10)

Two banks of 8 pads each (4 top / 4 bottom per bank):

**Bank 1** — chains 0, 1, 2 + master:

| Pad | Row    | CC  | Function     | Chain |
|-----|--------|-----|--------------|-------|
| 0   | Top    | 105 | Solo toggle  | 0     |
| 1   | Top    | 106 | Solo toggle  | 1     |
| 2   | Top    | 107 | Solo toggle  | 2     |
| 3   | Top    | 112 | Solo toggle  | 7/master |
| 4   | Bottom | 89  | Mute toggle  | 0     |
| 5   | Bottom | 90  | Mute toggle  | 1     |
| 6   | Bottom | 91  | Mute toggle  | 2     |
| 7   | Bottom | 96  | Mute toggle  | 7/master |

**Bank 2** — chains 3, 4, 5, 6:

| Pad | Row    | CC  | Function     | Chain |
|-----|--------|-----|--------------|-------|
| 0   | Top    | 108 | Solo toggle  | 3     |
| 1   | Top    | 109 | Solo toggle  | 4     |
| 2   | Top    | 110 | Solo toggle  | 5     |
| 3   | Top    | 111 | Solo toggle  | 6     |
| 4   | Bottom | 92  | Mute toggle  | 3     |
| 5   | Bottom | 93  | Mute toggle  | 4     |
| 6   | Bottom | 94  | Mute toggle  | 5     |
| 7   | Bottom | 95  | Mute toggle  | 6     |

### Pad LED Colors

| State     | Color          | RGB           |
|-----------|----------------|---------------|
| Solo ON   | Bright green   | (124, 184, 90)|
| Solo OFF  | Dim cyan       | (0, 40, 40)   |
| Mute ON   | Bright red     | (255, 0, 0)   |
| Mute OFF  | Dim purple     | (40, 0, 40)   |
| No chain  | Off            | (0, 0, 0)     |

LEDs update in real-time when mute/solo state changes (from any source).

---

## USB MIDI Ports

The SMK25 exposes 3 USB MIDI ports:

| Port   | Name (ALSA)   | Purpose                               |
|--------|---------------|---------------------------------------|
| Port 1 | SINCO OUT 1   | **Private / SysEx** — configuration   |
| Port 2 | SINCO OUT 2   | **Master** — normal MIDI I/O          |
| Port 3 | SINCO OUT 3   | Unused                                |

The driver listens on `SINCO IN 2` (Master input) for knobs/pads/transport,
and writes SysEx configuration to `SINCO OUT 1` (Private output).

---

## SysEx Protocol

### Overview

The SMK25 stores its configuration in internal flash. The SysEx protocol
allows writing flash regions. All SysEx is sent over the Private port
(Port 1) for USB, or via BLE GATT for Bluetooth.

**Important:** The device is write-only — it never sends SysEx responses.
See [Protocol Limitations](#protocol-limitations).

### 7-Bit Encoding

Over USB, all raw payloads are encoded into a 7-bit SysEx-safe bitstream
before being framed with `F0`/`F7`. Over BLE GATT, packets are sent raw
(no 7-bit encoding needed).

The encoding packs 8-bit bytes into 7-bit chunks in LSB-first order:

```python
def encode_7bit(data):
    result = bytearray()
    acc = 0
    bits = 0
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
```

### Flash Types

| FlashType | Purpose                         | Total Size |
|-----------|---------------------------------|------------|
| 4         | Device config / preset switching | 0x0C bytes |
| 5         | Preset configuration            | 0xED0 bytes (8 × 0x1DA) |

### Write Command (0x22)

Raw packet layout (before 7-bit encoding):

```
Offset  Size  Field
0x00    1     Manufacturer ID byte 1 (0x00)
0x01    1     Manufacturer ID byte 2 (0x59)
0x02    1     Command: 0x22 (Write)
0x03    3     Body size (LE) = data_len + 8
0x06    1     FlashType (0x04 or 0x05)
0x07    4     Flash address (LE, 32-bit)
0x0B    3     Data length (LE)
0x0E    N     Data bytes
0x0E+N  1     Checksum = ~sum(body_bytes) & 0xFF
```

The **body** for checksum starts at the FlashType byte (offset 0x06) and
includes everything through the data bytes (excluding the checksum itself).

### Commit / Save Command

A write command with `data_len = 0` serves as the commit/save command.
The device persists all pending writes to flash when it receives this.

```
Raw: [0x00, 0x59, 0x22, 0x08, 0x00, 0x00,
      FlashType,                     # 0x04 or 0x05
      addr_lo, addr_hi, 0x00, 0x00,  # Flash address (LE)
      0x00, 0x00, 0x00,              # data_len = 0 (commit)
      checksum]
```

### Read Command (0x23)

The protocol includes a read command (0x23) with the same packet structure
as write. However, the SMK25 is **write-only** — it does not respond to
read requests on any port (Private, Master, or Port 3). This was confirmed
by probing all three ports with read requests of various sizes.

### Chunked Writes

The device has limited SysEx buffer size. For large writes, split data into
64-byte (0x40) chunks with a 30ms inter-packet delay:

```python
for offset in range(0, len(data), 64):
    chunk = data[offset:offset + 64]
    write_flash(base_addr + offset, chunk)
    sleep(0.03)
commit_flash(base_addr)
```

### Checksum Algorithm

The checksum is the one's complement of the sum of all body bytes:

```python
checksum = (~sum(body_bytes)) & 0xFF
```

The body spans from the FlashType byte through the data bytes (excluding
the checksum byte itself).

---

## Flash Preset Layout

### FlashType 4 — Device Header

FlashType 4 stores 0x0C bytes of device configuration, primarily the
active preset index. It is written during [preset switching](#preset-switching)
at even offsets 0x00–0x0A with `[preset_index, 0x00]` pairs.

### FlashType 5 — Preset Storage

FlashType 5 contains 8 presets at `PRESET_STRIDE = 0x1DA` (474) bytes each.

| Preset | UI Label   | Flash Offset |
|--------|------------|--------------|
| 1      | Preset 1   | 0x0000       |
| 2      | Preset 2   | 0x01DA       |
| 3      | Preset 3   | 0x03B4       |
| 4      | Preset 4   | 0x058E       |
| 5      | Preset 5   | 0x0768       |
| 6      | Preset 6   | 0x0942       |
| 7      | Preset 7   | 0x0B1C       |
| 8      | Preset 8   | 0x0CF6       |

### Single Preset Layout (474 bytes)

```
Offset  Size  Region
0x000     4   Global flags (zeros for default)
0x004     1   Pitch bend range (0x7F = full)
0x005    25   Keyboard note offsets (25 keys, 0-based chromatic)
0x01E    70   Transport Button 1 (PLAY)
0x064    70   Transport Button 2 (STOP)
0x0AA    70   Transport Button 3 (REC)
0x0F0    48   Knob Page 1 (8 × 6 bytes)
0x120    48   Knob Page 2 (8 × 6 bytes)
0x150    64   Pad Bank 1  (8 × 8 bytes)
0x190    64   Pad Bank 2  (8 × 8 bytes)
0x1D0    10   Tail settings (velocity curve, aftertouch, etc.)
```

### Global Header

Bytes 0x000–0x004. First 4 bytes are flags (zeros for default). Byte 0x004
is pitch bend range (0x7F = full / 127).

### Keyboard Note Offsets

Bytes 0x005–0x01D (25 bytes). Standard chromatic mapping: key N plays
note (base + N), stored as `[0, 1, 2, ..., 24]`.

### Transport Button Entries

Each transport button occupies a 70-byte (0x46) block, mostly zeros:

```
Offset  Field
+0x00   Reserved (0)
+0x01   Reserved (0)
+0x02   CC number
+0x03   CC value (1)
+0x04   ... zeros through +0x45
```

### Knob Entries

8 knobs per page, 6 bytes each:

```
Offset  Field
+0x00   Type: 0x00=CC-Standard, 0x01=CC-Toggle, 0x03=CC-CW (encoder)
+0x01   Speed: 0x00=Free, 0x01=Slow, 0x02=Normal
+0x02   Channel (0x00 = channel 1)
+0x03   CC number
+0x04   Left value (min)
+0x05   Right value (max)
```

For CW-encoder knobs used in this driver: `type=0x03, left=0, right=1`.

### Pad Entries

8 pads per bank, 8 bytes each:

```
Offset  Field
+0x00   Type: 0x00=CC-Momentary, 0x01=CC-Toggle, 0x02=Note, 0x09=Note-Ch10
+0x01   Sub mode: 0x09 = MIDI channel 10
+0x02   Note/CC number
+0x03   MIDI channel (0x00)
+0x04   Velocity (0x7F = 127)
+0x05   Red (0-255)
+0x06   Green (0-255)
+0x07   Blue (0-255)
```

### Tail Settings

10 bytes at the end of each preset:

```
Offset  Field
+0x00   Reserved (0)
+0x01   Reserved (0)
+0x02   Velocity curve (0x01)
+0x03   Reserved (0)
+0x04   Max velocity (0x7F = 127)
+0x05   Reserved (0)
+0x06   Reserved (0)
+0x07   Aftertouch sensitivity (0x40 = 64)
+0x08   Reserved (0)
+0x09   Pitch bend range (0x7F = 127)
```

---

## Pad LED Control

### LED Update Protocol

Writing pad LED colors uses the same flash write protocol (FlashType 5),
targeting the RGB bytes (offset +5, +6, +7) within each pad entry at the
preset's flash address. Only 3 bytes need to be written per pad to change
the color without affecting the pad's CC/type/channel config.

### Pad 0 Refresh Trigger

The device refreshes pad LEDs only after writing to **pad 0 of bank 1**
followed by a commit. The driver exploits this by always writing pad 0
last before issuing the commit packet.

### Full LED Update Cycle

1. Write RGB for bank 1 pads 1–7
2. Write RGB for all bank 2 pads
3. Write RGB for bank 1 pad 0 (triggers refresh)
4. Send commit packet

Inter-packet delay: 20ms between writes.

### Single-Pad Fast Update

For toggling a single mute/solo:

1. Write RGB for the affected pad
2. Write RGB for bank 1 pad 0 (if not already pad 0)
3. Send commit packet

### Address Calculation

```
PAD_BASE_ADDR = 0x150  (within preset)
PRESET_8_OFFSET = 7 × 0x1DA = 0x0CF6
FLASH_BASE = PAD_BASE_ADDR + PRESET_8_OFFSET = 0x0E46

Pad N in bank B:
  addr = FLASH_BASE + (bank_offset) + (N × 8) + 5
  bank 1 offset = 0x00, bank 2 offset = 0x40
```

---

## Preset Switching

Switching the active preset on the device requires a specific sequence
discovered via binary-search testing with live hardware. Neither SysEx
primers alone nor FlashType 4 writes alone are sufficient — both are
required in the correct order with proper timing.

### Minimal Sequence

```
1.  Send SysEx primer A:  raw [0x00, 0x59, PRESET_IDX]
2.  Send SysEx primer B:  raw [0x00, 0x59, 0x22, PRESET_IDX]
3.  Wait ~200ms
4.  FlashType 4 write at offset 0x00: [PRESET_IDX, 0x00]
5.  FlashType 4 write at offset 0x02: [PRESET_IDX, 0x00]
6.  FlashType 4 write at offset 0x04: [PRESET_IDX, 0x00]
7.  FlashType 4 write at offset 0x06: [PRESET_IDX, 0x00]
8.  FlashType 4 write at offset 0x08: [PRESET_IDX, 0x00]
9.  FlashType 4 write at offset 0x0A: [PRESET_IDX, 0x00]
10. FlashType 4 commit (data_len = 0)
```

`PRESET_IDX` is 0-based (0 = Preset 1, 7 = Preset 8). The 30ms
inter-packet delay between FlashType 4 writes is required.

### Key Findings

- **Both primers required.** Either primer alone + FT4 writes fails.
- **Timing is critical.** The ~200ms gap between primers and FT4 writes
  is required. Without it, the same bytes sent in rapid succession fail.
- **Over USB**, primers are 7-bit encoded and wrapped in F0/F7 like all SysEx.
- **Over BLE**, primers are sent as raw packets (no encoding).
- After switching, allow ~1.5s for the device to settle before writing
  pad LED colors.

### Driver Integration

The driver calls `_switch_preset()` at the end of `_write_preset_config()`,
then waits 1.5s before writing initial LED colors:

```python
self._write_preset_config()  # 474 bytes in 64-byte chunks
self._switch_preset(7)       # Switch to preset 8
sleep(1.5)                   # Let device settle
self._update_pad_leds()      # Now safe to set LED colors
```

---

## .mkc File Format

The `Loadtopreset8inmidisuite.mkc` file is exactly 474 bytes — one raw
preset blob with no framing or headers. It maps 1:1 to a single preset
region in FlashType 5 flash.

To load it via MidiSuite: import and assign to preset 8. To load it via
this driver: it happens automatically on every startup (the driver
constructs the same data programmatically from its constants).

---

## Protocol Limitations

| Limitation | Details |
|------------|---------|
| **Write-only** | The device never sends SysEx responses. Read commands (0x23) are accepted but produce no reply on any port. |
| **No heartbeat** | No periodic status messages. No way to verify the device is alive other than trying a write. |
| **No device ID query** | No SysEx identity request/response. Device detected only by USB VID/PID or BLE device name. |
| **Timing-sensitive** | Preset switching fails without proper inter-message delays (~200ms between primers and FT4 writes). |
| **Flash wear** | Every LED update writes to flash. The driver minimizes writes with dirty-flag coalescing and single-pad fast updates. |
| **Pad 0 trigger** | LED refresh only fires after writing pad 0 of bank 1 + commit. |
| **Buffer limits** | SysEx packets must be chunked to ≤64 bytes with 30ms inter-packet delays. |

---

## Bluetooth LE (BLE) Support

### Connection Details

| Property | Value |
|----------|-------|
| Device name | `SMK25V2` |
| GATT characteristic UUID | `0000ae41-0000-1000-8000-00805f9b34fb` |
| BlueZ device path (example) | `/org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX` |

### USB vs BLE Differences

| Aspect | USB | BLE |
|--------|-----|-----|
| Transport | SysEx on Private port (Port 1) | GATT `WriteValue()` on vendor characteristic |
| Encoding | 7-bit encoded, `F0`/`F7` framed | Raw packets (no encoding) |
| MIDI ports | 3 ports (Private, Master, Port 3) | Single BLE MIDI port |
| MIDI input | Listens on `SINCO IN 2` | Listens on `SMK25V2 IN` |
| Primer messages | `_send_sysex()` (7-bit encoded) | `_gatt_write(_build_raw_packet())` |
| Inter-packet delay | 30ms (SysEx) | 20ms (GATT) |
| Driver class | `zynthian_ctrldev_sinco_smk25` | `zynthian_ctrldev_sinco_smk25_bt` |

The BT driver uses D-Bus to discover the BlueZ GATT characteristic at
startup. All flash write/commit/preset-switch logic is identical — only
the transport layer differs.

---

## Driver Architecture

### Threads

| Thread                 | Purpose                                         |
|------------------------|-------------------------------------------------|
| `smk25-preset-config`  | Writes preset → switches preset → updates LEDs |
| `smk25-led-worker`     | Persistent worker; waits for dirty flag         |

The preset-config thread handles the full startup sequence: write 474-byte
preset in 64-byte chunks → switch to preset → wait 1.5s → write initial
LED colors. This ensures LEDs are set only after the preset is active.

### Event Flow

```
USB MIDI (Port 2) → midi_event()
  ├─ CC on ch0 → knob/transport handler → send_cuia()
  └─ CC on ch9 → _handle_pad() → toggle mute/solo → _write_single_pad_led()

Chain state change → update_mixer_strip() / refresh()
  → _led_dirty.set() → _led_worker_loop() → _update_pad_leds()
```

### LED Update Coalescing

The LED worker uses a `threading.Event` dirty flag. Multiple rapid state
changes (e.g. loading a snapshot) coalesce into a single LED update cycle.
A `threading.Lock` prevents concurrent flash writes from overlapping.

### Debouncing

The SELECT/BACK knob (CC 27) has a 600ms debounce to prevent accidental
double-triggers (physical encoder detent bounce).

---

## Testing

### Test Suite

`test_device.py` contains 35 tests in 5 groups:

| Group | Tests | Requires Device |
|-------|-------|-----------------|
| `TestPacketBuilding` | 5 | No |
| `TestPresetData` | 12 | No |
| `TestDevicePorts` | 3 | Yes |
| `TestDeviceSysEx` | 2 | Yes |
| `TestDevicePadLEDs` | 3 | Yes |
| `TestDevicePresetWrite` | 1 | Yes |

Run all tests:

```bash
python -m unittest test_device -v
```

Device-dependent tests are automatically skipped when the SMK25 is not
connected. When connected, all 35 tests pass.

### Probe Scripts

| Script | Purpose |
|--------|---------|
| `probe_device.py` | Sends SysEx read/write on Private port, listens for responses |
| `probe_all_ports.py` | Probes all 3 USB MIDI ports for any SysEx response |
| `test_preset_switch.py` | Tests 7 individual preset switching approaches |
| `test_preset_switch_combo.py` | Tests combinations of switching approaches |
| `test_preset_switch_narrow.py` | Tests SysEx primer variants + timing |

---

## SMK25 vs SMC-PAD Differences

The SMK25 protocol was reverse-engineered from the SINCO MidiSuite desktop
app (see [claudepad](https://github.com/malpern/claudepad)). The same app
supports both the SMK25 keyboard controller and the SMC-PAD pad controller.

Key differences in the decompiled code:

| Aspect | SMK25 | SMC-PAD |
|--------|-------|---------|
| FlashType | 5 (presets), 4 (device header) | 5 (presets), 4 (device header) |
| Preset size | 474 bytes (0x1DA) | Different (pad-only layout) |
| Has keyboard | Yes (25 keys) | No |
| Has knobs | Yes (8 encoders, 2 pages) | No |
| Has transport | Yes (Play/Stop/Rec) | No |
| Pad count | 16 (2 banks × 8) | Varies by model |
| USB VID:PID | 0x4353:0x4B4D | TBD |

The `SmcPad::loadData()` and `sendDataToDevice()` functions in MidiSuite
handle both device types. The flash write/commit protocol is identical;
only the preset data layout differs.

---

## References

- [claudepad](https://github.com/malpern/claudepad) — Ghidra decompilation
  of the MidiSuite desktop app, including `SmcPad::loadData()`,
  `sendDataToDevice()`, and full flash protocol findings.
- `Loadtopreset8inmidisuite.mkc` — reference preset file (474 bytes).
- `test_device.py` — test suite (35 tests) covering packet building,
  preset data, live device writes, and LED control.
- `parse_mkc.py` / `parse_mkc_deep.py` — .mkc file analysis tools.
- `midi_cc_map.md` — original CC mapping notes.

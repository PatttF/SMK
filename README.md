# SMK — SINCO SMC-PAD Pocket Knob Configuration

Set all 8 knobs across all 8 presets on the **SINCO SMC-PAD Pocket** to
**CC Relative mode**, so the top-row knobs send raw `+1`/`-1` relative CC
data and can be used as Zynpots on a [Zynthian](https://zynthian.org) system.

---

## Why?

By default the **SINCO SMC-PAD Pocket** (also sold as the SMK-25) sends absolute CC values (0–127) from
its knobs. Zynthian's *zynpots* require relative CC data (`+1`/`-1`). Rather
than intercepting and translating the data in software, we write **type byte
`0x01` (CC Relative)** directly to the device's flash memory via SysEx so the
hardware itself sends relative data on every preset.

The knob type byte address and SysEx flash-write protocol were determined by
Ghidra decompilation of the official **MidiSuite** application.

---

## Prerequisites

```bash
pip install mido python-rtmidi
```

The scripts require the **`SINCO SMC-PAD Pocket-Private`** virtual USB MIDI
port to be visible. Plug in the device before running.

---

## Usage

### 1 — Write CC Relative to all knobs

```bash
python set_knobs_relative.py
```

This will:

1. Open the `…Private` MIDI port.
2. For each of the **8 presets × 8 knobs** (64 writes total), compute the
   flash address and send a SysEx flash-write packet containing `0x01`.
3. Send a flash save/commit command.
4. Print progress for every write.

Example output:

```
Opened port: SINCO SMC-PAD Pocket-Private
Setting preset 0 knob 0 @ flash addr 0x0073 → 0x01
Setting preset 0 knob 1 @ flash addr 0x0079 → 0x01
…
Setting preset 7 knob 7 @ flash addr 0x6162 → 0x01
Sending flash save/commit…
Done. Power-cycle the SMC-PAD to apply changes.
```

### 2 — Power-cycle the device

⚠️ **The SMC-PAD must be power-cycled (unplugged and re-plugged) for the
new flash settings to take effect.**

### 3 — Verify

```bash
python verify_knobs.py
```

Reads back the type byte for every knob and reports pass/fail:

```
Preset 0 Knob 0 @ 0x0073: ✓ CC Relative (0x01)
Preset 0 Knob 1 @ 0x0079: ✓ CC Relative (0x01)
…
All knobs verified as CC Relative (0x01). ✓
```

---

## Knob type values

| Byte | Mode            |
|------|-----------------|
| 0x00 | CC Absolute     |
| 0x01 | CC Relative ← **target** |
| 0x02 | Note            |
| 0x03 | Program Change  |
| 0x04 | Disabled/SysEx  |

---

## Protocol notes

All SysEx data sent to the device is **7-bit packed** (every 7 input bytes →
8 output bytes, MSBs collected into a leading prefix byte) inside a standard
`F0 … F7` SysEx frame.

The knob type byte address formula (from decompiled `FUN_100041160`):

```
flash_addr = (preset × 0xDD3) + (knob_index × 6) + 0x73
```

- `preset`: 0–7
- `knob_index`: 0–7
- `FlashType`: 5

---

## Scope

Both scripts target **all 8 knobs across all 8 presets**, so no matter which
preset is active, every knob sends relative CC data. Only the top-row knobs
will actually be wired to Zynpots, but setting all of them ensures a
consistent experience across preset changes.

---

## Connecting to Zynthian

After power-cycling, configure Zynthian to listen for relative CC on the knob
CC numbers (check your current assignment via `aseqdump` on the Pi). Map those
CCs to `zynpot_0` through `zynpot_3` in Zynthian's web UI under
**MIDI → Zynpots**.
# SMK

Scripts for configuring the SINCO SMC-PAD Pocket via SysEx.

## Requirements

```
pip install mido python-rtmidi
```

Connect the SMC-PAD Pocket via USB before running any script.

---

## set_knobs_relative.py

Sets **all 8 knobs across all 8 presets** to CC Relative mode with known CC
numbers and MIDI channel 15.

| Knob | CC  | Channel | Mode        |
|------|-----|---------|-------------|
| 1    | 70  | 15      | CC Relative |
| 2    | 71  | 15      | CC Relative |
| 3    | 72  | 15      | CC Relative |
| 4    | 73  | 15      | CC Relative |
| 5    | 74  | 15      | CC Relative |
| 6    | 75  | 15      | CC Relative |
| 7    | 76  | 15      | CC Relative |
| 8    | 77  | 15      | CC Relative |

For each knob the script reads the existing 6-byte flash struct, modifies only
bytes 0 (type), 1 (CC), and 2 (channel), and writes all 6 bytes back to
preserve any unknown fields.  A flash save/commit is sent at the end.

```
python set_knobs_relative.py
```

**Power-cycle the SMC-PAD after running the script to apply the changes.**

---

## verify_knobs.py

Reads back every knob's 6-byte struct and prints a verification table.
Exits with a non-zero status if any knob does not match the expected values.

```
python verify_knobs.py
```

Expected output (all OK — values are shown in hexadecimal; cc=46 is CC 70, cc=47 is CC 71, etc.):
```
Preset 0 Knob 0 @ 0x0073: type=01 cc=46 ch=0e rest=... [OK]
Preset 0 Knob 1 @ 0x0079: type=01 cc=47 ch=0e rest=... [OK]
...
All knobs verified OK.
```

---

## MIDI CC Map

See [`midi_cc_map.md`](midi_cc_map.md) for the full CC reference, including
pad note assignments and Zynthian zynpot wiring.

### Zynthian zynpot wiring

Top-row knobs (1–4) emit CC Relative messages on **channel 15, CC 70–73**.
Wire them to zynpots 0–3 in Zynthian's MIDI configuration:

```
zynpot_0 → CC 70, channel 15
zynpot_1 → CC 71, channel 15
zynpot_2 → CC 72, channel 15
zynpot_3 → CC 73, channel 15
```
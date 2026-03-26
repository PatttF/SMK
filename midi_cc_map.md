# SMC-PAD Pocket — MIDI CC Map

## Knobs (after running set_knobs_relative.py)

| Knob | Position         | CC  | Channel | Mode        |
|------|------------------|-----|---------|-------------|
| 1    | Top-left         | 70  | 15      | CC Relative |
| 2    | Top-center-left  | 71  | 15      | CC Relative |
| 3    | Top-center-right | 72  | 15      | CC Relative |
| 4    | Top-right        | 73  | 15      | CC Relative |
| 5    | Bot-left         | 74  | 15      | CC Relative |
| 6    | Bot-center-left  | 75  | 15      | CC Relative |
| 7    | Bot-center-right | 76  | 15      | CC Relative |
| 8    | Bot-right        | 77  | 15      | CC Relative |

## Why CC 70–77?

Standard MIDI CC assignments (GM/GS spec):
- CC 1: Mod Wheel
- CC 7: Channel Volume
- CC 10: Pan
- CC 11: Expression
- CC 64: Sustain Pedal
- CC 65–69: Portamento, Sostenuto, Soft Pedal, Legato, Hold 2
- **CC 70–79: Sound Controllers (largely unassigned in practice)** ← we use 70–77
- CC 91–95: Effects depths
- CC 120–127: Channel mode messages (reserved)

## Pads

| Row | Pad | Note | Channel |
|-----|-----|------|---------|
| 1   | 1   | 36   | 10      |
| 1   | 2   | 37   | 10      |
| 1   | 3   | 38   | 10      |
| 1   | 4   | 39   | 10      |
| 2   | 5   | 40   | 10      |
| 2   | 6   | 41   | 10      |
| 2   | 7   | 42   | 10      |
| 2   | 8   | 43   | 10      |
| 3   | 9   | 44   | 10      |
| 3   | 10  | 45   | 10      |
| 3   | 11  | 46   | 10      |
| 3   | 12  | 47   | 10      |
| 4   | 13  | 48   | 10      |
| 4   | 14  | 49   | 10      |
| 4   | 15  | 50   | 10      |
| 4   | 16  | 51   | 10      |

## Zynthian Zynpot Wiring

Top-row knobs (1–4) map to zynpots 0–3 via CC 70–73 on channel 15.

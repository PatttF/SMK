# SINCO SMK25 — MIDI CC Map

## Knobs (configured via 25KEY editor, Left=0, Right=1)

| Knob | CC  | Channel | Range | Zynpot |
|------|-----|---------|-------|--------|
| 1    | 20  | 1       | 0–1   | 0      |
| 2    | 21  | 1       | 0–1   | 1      |
| 3    | 22  | 1       | 0–1   | 2      |
| 4    | 23  | 1       | 0–1   | 3      |
| 5    | 24  | 1       | 0–127 | —      |
| 6    | 25  | 1       | 0–127 | —      |
| 7    | 26  | 1       | 0–127 | —      |
| 8    | 27  | 1       | 0–127 | —      |

Knobs 1–4: Type=CW, Left=0, Right=1.  Value 0 = CCW (−1), value 1 = CW (+1).
The driver treats these as relative encoders sending delta ±1 to ZYNPOT.

Knobs 5–8: Type=CW, Left=0, Right=127.  Standard absolute CC. Pass through.

## Preset file format (preset.mkc)

Each knob entry is 6 bytes:
```
byte 0: type (0x03 = CW with range, 0x00 = standard CW)
byte 1: speed (0x02 = Normal)
byte 2: channel (0x00 = ch 1)
byte 3: CC number
byte 4: left (min value)
byte 5: right (max value)
```

## Zynthian driver

Port matching: `dev_ids = ["SINCO IN 1"]`
CC 20–23 on channel 0 (wire) → ZYNPOT 0–3 via delta ±1.

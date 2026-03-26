# SMK

## Zynthian Driver

The file `zyngine/ctrldev/zynthian_ctrldev_sinco_smc_pad_pocket.py` is a
zynthian_ctrldev driver. Copy it to your Zynthian's
`/zynthian/zynthian-ui/zyngine/ctrldev/` directory.

On driver load (device connect), it automatically configures all 8 knobs
across all 8 presets to CC Relative mode (CC 70–77, channel 15) via SysEx
flash writes. Power-cycle the device after first connect to apply.

Top-row knobs (CC 70–73) drive Zynthian's zynpots 0–3.

Note: The device name in `dev_ids` may need adjusting — run
`set_knobs_relative.py` first with `mido` to confirm your device's MIDI port name,
then update `dev_ids` accordingly.
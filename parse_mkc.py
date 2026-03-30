#!/usr/bin/env python3
"""Parse and annotate the .mkc preset file for the SINCO SMK25."""

import sys

data = open('Loadtopreset8inmidisuite.mkc', 'rb').read()
print(f'Total size: {len(data)} bytes (0x{len(data):X})')
print(f'Expected PRESET_STRIDE: 0x1DA = {0x1DA}')
print()

# Raw hex dump
print('=== Raw byte dump with offsets ===')
for i in range(0, len(data), 16):
    hex_part = ' '.join(f'{b:02X}' for b in data[i:i+16])
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
    print(f'  {i:04X}: {hex_part:<48s} {ascii_part}')

# From the decompile:
# - flash_read(5, 0, this+0x54, 0x6E98)  => 0x6E98 total for 8 presets
# - 0x6E98 / 8 = 0xDD3 per preset (3539 bytes) -- that's SmcPad (16-pad device)
# - SMK25 uses PRESET_STRIDE = 0x1DA (474 bytes)
# - 0x1DA * 8 = 0xED0 total for 8 presets
# - The .mkc file is 474 bytes = exactly 1 preset (0x1DA)!

print()
print(f'File is exactly 1 preset: {len(data)} == {0x1DA} (PRESET_STRIDE)')
print()

# Knob region
# From midi_cc_map.md: 6 bytes per knob [type, speed, channel, CC, left, right]
# From the decompile: knob data at preset_offset + some_base
# The Smk25Dlg colorChanged uses: addr = 0x155 + (pad_index * 0x1DA) + (bank_index * 8)
# Wait - that's for SmcPad pad colors. For SMK25:
#   Pad base = 0x150 within a preset
#   Knob section comes before pads
# Let's figure out knob region from the data

print('=== Knob data (6 bytes each, starting at various offsets) ===')
# Try offset 0xF0 which is where we see the pattern 03 02 00 14 00 01
knob_base = 0xF0
for i in range(16):
    offset = knob_base + i * 6
    if offset + 6 <= len(data):
        chunk = data[offset:offset+6]
        # type: 0x03=CW, 0x00=standard
        # speed: 0x02=Normal, 0x01=?, 0x00=?
        types = {0: 'CC-Std', 1: 'CC-Toggle', 2: 'Note', 3: 'CC-CW'}
        type_str = types.get(chunk[0], f'0x{chunk[0]:02X}')
        print(f'  Knob {i+1:2d}: offset=0x{offset:04X} type={type_str}({chunk[0]:02X}) speed={chunk[1]:02X} ch={chunk[2]+1} cc={chunk[3]} left={chunk[4]} right={chunk[5]}')
    else:
        break

print()
print('=== Pad data (8 bytes each, starting at 0x150) ===')
pad_base = 0x150
for i in range(16):
    offset = pad_base + i * 8
    if offset + 8 <= len(data):
        chunk = data[offset:offset+8]
        pad_types = {0: 'CC-Momentary', 1: 'CC-Toggle', 2: 'Note', 9: 'Note-Ch10'}
        type_str = pad_types.get(chunk[0], f'0x{chunk[0]:02X}')
        print(f'  Pad {i+1:2d}: offset=0x{offset:04X} type={type_str}({chunk[0]:02X}) sub={chunk[1]:02X} note/cc={chunk[2]} ch={chunk[3]+1} vel={chunk[4]} R={chunk[5]:3d} G={chunk[6]:3d} B={chunk[7]:3d}')
    else:
        print(f'  Pad {i+1:2d}: offset=0x{offset:04X} -- beyond file')

print()
print('=== Region before knobs (0x00-0xEF) ===')
# Bytes 0x00-0x03: Global header?
print(f'  0x00-0x03: {" ".join(f"{b:02X}" for b in data[0:4])}  (header/flags)')
print(f'  0x04:      {data[4]:02X} = {data[4]}  (pitch bend range? 127=full)')
# Bytes 0x05-0x18: 20-byte array (0x00 to 0x18 = CC numbers 0-24)?
print(f'  0x05-0x18: MIDI channel assignment table?')
for j in range(0, 20, 10):
    chunk = data[5+j:5+j+10]
    print(f'    +{j:02X}: {" ".join(f"{b:02X}" for b in chunk)}')

# Bytes 0x19-0x1A
print(f'  0x19-0x1A: {data[0x19]:02X} {data[0x1A]:02X}')

# Bytes 0x1B-0x1C: interesting - 0x66 0x01 = 0x166 = 358?
print(f'  0x1B-0x1C: {data[0x1B]:02X} {data[0x1C]:02X} (={data[0x1B] + data[0x1C]*256})')

# Bytes 0x1D-0x65: all zeros (transport/button config area?)
print(f'  0x1D-0x65: all zeros (transport button area?)')
nonzero = [(i, data[i]) for i in range(0x1D, 0x66) if data[i] != 0]
if nonzero:
    print(f'    Non-zero: {nonzero}')
else:
    print(f'    (confirmed all zeros)')

# 0x66-0x67: 0x67 0x01
print(f'  0x66-0x67: {data[0x66]:02X} {data[0x67]:02X} (={data[0x66] + data[0x67]*256})')

# 0x68-0xA5: zeros
print(f'  0x68-0xA5: all zeros?')
nonzero = [(i, data[i]) for i in range(0x68, 0xA6) if data[i] != 0]
if nonzero:
    print(f'    Non-zero: {nonzero}')
else:
    print(f'    (confirmed all zeros)')

# 0xA6-0xA7: 0x68 0x01
print(f'  0xA6-0xA7: {data[0xA6]:02X} {data[0xA7]:02X} (={data[0xA6] + data[0xA7]*256})')

# 0xA8-0xEF: zeros
print(f'  0xA8-0xEF: all zeros?')
nonzero = [(i, data[i]) for i in range(0xA8, 0xF0) if data[i] != 0]
if nonzero:
    print(f'    Non-zero: {nonzero}')
else:
    print(f'    (confirmed all zeros)')

print()
print('=== Post-pad data (0x1D0 onwards) ===')
for i in range(0x1D0, len(data)):
    if data[i] != 0:
        print(f'  0x{i:04X}: {data[i]:02X}')

print()
print('=== Summary ===')
print(f'  Global header:        0x000 - 0x01A  (27 bytes)')
print(f'  Transport buttons(?): 0x01B - 0x0EF  (213 bytes, 3 non-zero pairs)')
print(f'  Knob config (page1):  0x0F0 - 0x11F  (48 bytes = 8 knobs * 6)')
print(f'  Knob config (page2):  0x120 - 0x14F  (48 bytes = 8 knobs * 6)')
print(f'  Pad bank 1:           0x150 - 0x18F  (64 bytes = 8 pads * 8)')
print(f'  Pad bank 2:           0x190 - 0x1CF  (64 bytes = 8 pads * 8)')
print(f'  Tail:                 0x1D0 - 0x1D9  (10 bytes)')

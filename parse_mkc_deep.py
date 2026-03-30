#!/usr/bin/env python3
"""Deep analysis of the .mkc file transport/button and tail regions."""

data = open('/Users/pat/Downloads/SMK-main/Loadtopreset8inmidisuite.mkc', 'rb').read()

print('=== Global header (0x00-0x04) ===')
for i in range(5):
    print(f'  0x{i:02X}: {data[i]:02X} = {data[i]}')

print()
print('=== Keyboard note offset table (0x05-0x1D) ===')
for i in range(25):
    print(f'  Key {i+1:2d}: note offset = {data[5+i]:3d} (0x{data[5+i]:02X})')

print()
print('=== Non-zero bytes in 0x1E-0xEF ===')
for i in range(0x1E, 0xF0):
    if data[i] != 0:
        print(f'  0x{i:04X}: {data[i]:02X} = {data[i]}')

print()
# Pattern: non-zero at 0x20,0x21 and 0x66,0x67 and 0xAC,0xAD
# 0x20: 66=102(CC_PLAY), 0x21: 01=val1
# 0x66: 67=103(CC_STOP), 0x67: 01=val1
# 0xAC: 68=104(CC_REC),  0xAD: 01=val1
# Stride = 0x66-0x20 = 0x46 = 70 bytes between each button!
# BUT... 0x20-0x1E=2 bytes before CC => those 2 bytes are the button struct header

print('=== Transport button analysis ===')
btn_stride = 0x46  # 70 bytes
print(f'  Stride: {btn_stride} bytes (0x{btn_stride:02X})')
names = ['PLAY', 'STOP', 'REC']
for b in range(3):
    base = 0x1E + b * btn_stride
    end = base + btn_stride
    chunk = data[base:end]
    print(f'\n  {names[b]} button (0x{base:04X}-0x{end-1:04X}):')
    print(f'    Hex: {" ".join(f"{v:02X}" for v in chunk[:10])} ...')
    nz = [(j, chunk[j]) for j in range(len(chunk)) if chunk[j] != 0]
    print(f'    Non-zero at relative offsets: {[(f"+{j}", f"0x{v:02X}={v}") for j, v in nz]}')

# 0x1E+3*0x46 = 0x1E + 0xD2 = 0xF0 => where knobs start. Perfect!
print(f'\n  3 buttons end at: 0x{0x1E + 3 * btn_stride:04X} (matches knob base 0x00F0)')

# The button struct within 0x46 bytes:
# For PLAY: +2=0x66(102), +3=0x01(1)
# This means: [byte0, byte1, CC, value, ...68 more zero bytes]
# But wait - the struct from setBtnData was 0x17 (23 bytes) per button
# 0x17 * 3 = 0x45 = 69, close to 70

# Actually looking at setBtnData: lVar4 = iVar2 * 0x17 + preset*0x0DD3
# That's for SmcPad. For SMK25, the stride is different.
# The file tells us: btn_stride = 0x46 = 70

print()
print('=== Tail data (0x1D0-0x1D9) ===')
tail = data[0x1D0:]
print(f'  Raw: {" ".join(f"{b:02X}" for b in tail)}')
print(f'  Length: {len(tail)} bytes')
for i, b in enumerate(tail):
    if b != 0:
        print(f'  +{i}: 0x{b:02X} = {b}')

print()
print()
print('========================================')
print('COMPLETE PRESET LAYOUT (474 = 0x1DA bytes)')
print('========================================')
print()
print('Offset  Size  Description')
print('------  ----  -----------')
print('0x000     4   Global flags (all zero in this preset)')
print('0x004     1   Pitch bend range (0x7F = 127 = full)')
print('0x005    25   Keyboard note offsets (0x00-0x18 = notes 0-24)')
print('0x01E    70   Transport Button 1 (PLAY): CC at +2, Value at +3')
print('0x064    70   Transport Button 2 (STOP): CC at +2, Value at +3')
print('0x0AA    70   Transport Button 3 (REC):  CC at +2, Value at +3')
print('0x0F0    48   Knob Page 1 (8 knobs x 6 bytes: type,speed,ch,cc,left,right)')
print('0x120    48   Knob Page 2 (8 knobs x 6 bytes)')
print('0x150    64   Pad Bank 1 (8 pads x 8 bytes: type,mode,note/cc,ch,vel,R,G,B)')
print('0x190    64   Pad Bank 2 (8 pads x 8 bytes)')
print('0x1D0    10   Tail (velocity/aftertouch/pedal settings)')
print()
print(f'Total:      {0x1DA} bytes (PRESET_STRIDE = 0x1DA)')
print(f'Full flash: {0x1DA * 8} bytes for 8 presets (0x{0x1DA * 8:04X} = 0xED0)')

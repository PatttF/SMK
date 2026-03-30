#!/usr/bin/env python3
"""Verify that _build_preset_data() produces identical output to the .mkc file.

We can't import the full driver (Zynthian deps), so we extract the module-level
constants and the standalone _build_preset_data() function manually.
"""

import re

SRC_PATH = '/Users/pat/Downloads/SMK-main/zyngine/ctrldev/zynthian_ctrldev_sinco_smk25.py'
MKC_PATH = '/Users/pat/Downloads/SMK-main/Loadtopreset8inmidisuite.mkc'

src = open(SRC_PATH).read()

# Extract everything before the class definition (constants)
pre_class = src.split('class zynthian_ctrldev_sinco_smk25')[0]
# Remove the import lines that need Zynthian
lines = []
for line in pre_class.splitlines():
    if line.startswith(('import ', 'from ')):
        continue
    lines.append(line)
constants_code = '\n'.join(lines)

# Extract _build_preset_data function (it's at module level, not indented)
match = re.search(r'^(def _build_preset_data\(\):.*?)(?=\ndef |\nclass |\Z)', src, re.DOTALL | re.MULTILINE)
if not match:
    raise RuntimeError("Could not find _build_preset_data")
func_code = match.group(1)

# Execute both in a shared namespace
ns = {}
exec(constants_code, ns)
exec(func_code, ns)

preset = ns['_build_preset_data']()
mkc = open(MKC_PATH, 'rb').read()

print(f"Generated preset: {len(preset)} bytes")
print(f"MKC file:         {len(mkc)} bytes")

if preset == mkc:
    print("\n*** PERFECT MATCH! ***")
else:
    diffs = 0
    for i in range(min(len(preset), len(mkc))):
        if preset[i] != mkc[i]:
            print(f"  Offset 0x{i:04X}: generated=0x{preset[i]:02X}  mkc=0x{mkc[i]:02X}")
            diffs += 1
    if len(preset) != len(mkc):
        print(f"  Length mismatch: {len(preset)} vs {len(mkc)}")
    print(f"\n  Total byte differences: {diffs}")

#!/usr/bin/env python3
# prints the NAME_ENTRIES block of src/model/reloc.mach from its ROWS, to paste after a kind is added
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "src/model/reloc.mach"
s = open(path).read()
names = dict(re.findall(r'pub val (\w+):\s+Kind = Kind\{name: "([^"]+)"', s))
a = s.index("val ROWS:")
ids = re.findall(r"\?(\w+)", s[a : s.index("};", a)])
entries = sorted((names[i], n) for n, i in enumerate(ids))
if len({e[0] for e in entries}) != len(entries):
    sys.exit("two kinds share a name")
print("val NAME_ENTRIES: [ROW_COUNT]Entry = [ROW_COUNT]Entry{")
for key, row in entries:
    print('    Entry{key: "%s", row: %d},' % (key, row))
print("};")

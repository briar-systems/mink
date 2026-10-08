#!/usr/bin/env bash
# compares two outputs of tools/shape/shape.sh, one from before a change and
# one after, and lists per structure what changed: newly read, newly holding
# raw bodies, newly refused (a regression to explain) and other differences.
#
# usage: bash tools/shape/delta.sh <before> <after>
set -u

[ $# -eq 2 ] || { echo "usage: bash tools/shape/delta.sh <before> <after>" >&2; exit 2; }

python3 -I - "$1" "$2" <<'PY'
import re, sys

def load(path):
    rows = {}
    with open(path) as f:
        for line in f:
            key, _, rest = line.rstrip("\n").partition("\t")
            rows[key] = rest
    return rows

def raw(rest):
    return sum(int(n) for n in re.findall(r"\b(?:raw|rawcommands|rawblobs|rawbytes)=(\d+)", rest))

before, after = load(sys.argv[1]), load(sys.argv[2])
groups = {"newly read": [], "newly holding raw": [], "newly refused": [], "other changes": []}
same = 0
for key in sorted(set(before) | set(after)):
    b, a = before.get(key), after.get(key)
    if b == a:
        same += 1
    elif b is None or a is None:
        groups["other changes"].append((key, b, a))
    elif b.startswith("refused") and a.startswith("read"):
        groups["newly read"].append((key, b, a))
    elif b.startswith("read") and a.startswith("refused"):
        groups["newly refused"].append((key, b, a))
    elif raw(a) > raw(b):
        groups["newly holding raw"].append((key, b, a))
    else:
        groups["other changes"].append((key, b, a))
print("unchanged: %d" % same)
for name, rows in groups.items():
    print("%s: %d" % (name, len(rows)))
    for key, b, a in rows:
        print("  %s\n    before: %s\n    after:  %s" % (key, b, a))
PY

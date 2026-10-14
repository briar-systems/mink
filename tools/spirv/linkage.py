#!/usr/bin/env python3
# copy SPIR-V modules as objects a link takes, for the neutral lane.
#
# run by hand: python3 -I tools/spirv/linkage.py <corpus> <out>, then
# test/run.sh --neutral <out>
# a module is an object a link takes when it declares the Linkage capability, and the
# neutral lane counts every other module out of scope. each .spv file under <corpus>
# is copied to <out>, numbered in sorted path order, with OpCapability Linkage put
# after its first capability when it declares none, in the byte order it is written
# in. nothing else changes, so every module joins the lane as itself.
# exits 1 when a file holds no module.

import os
import struct
import sys

MAGIC = 0x07230203
CAPABILITY = 17
LINKAGE = 5


def linked(data):
    for order in ("<", ">"):
        if len(data) >= 20 and struct.unpack(order + "I", data[:4])[0] == MAGIC:
            break
    else:
        return None
    n = len(data) // 4
    words = list(struct.unpack("%s%dI" % (order, n), data[: n * 4]))
    at = 5
    first = None
    while at < n:
        count, op = words[at] >> 16, words[at] & 0xFFFF
        if count == 0 or op != CAPABILITY:
            break
        if words[at + 1] == LINKAGE:
            return data
        if first is None:
            first = at + count
        at += count
    if first is None:
        first = 5
    words[first:first] = [(2 << 16) | CAPABILITY, LINKAGE]
    return struct.pack("%s%dI" % (order, len(words)), *words)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: linkage.py <corpus> <out>")
    corpus, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    paths = []
    for root, _, files in os.walk(corpus):
        paths += [os.path.join(root, f) for f in files if f.endswith(".spv")]
    bad = 0
    for i, path in enumerate(sorted(paths), 1):
        with open(path, "rb") as f:
            data = linked(f.read())
        if data is None:
            print("not a module: " + path)
            bad += 1
            continue
        with open(os.path.join(out, "%d.spv" % i), "wb") as f:
            f.write(data)
    print("%d modules copied to %s" % (len(paths) - bad, out))
    sys.exit(1 if bad else 0)


main()

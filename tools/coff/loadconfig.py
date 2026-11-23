#!/usr/bin/env python3
"""scan PE32 images for a load configuration whose process heap flags or process
affinity mask is not zero.

usage: python3 -I tools/coff/loadconfig.py <root>...

the PE Format page orders ProcessAffinityMask before ProcessHeapFlags in the
PE32 load configuration and winnt.h orders them the other way, so only an image
with one of the two set could settle the order. prints how many PE32 images were
scanned, how many have a load configuration of at least 0x34 bytes, and each one
that sets either word. nothing here runs in CI.
"""
import os
import struct
import sys

MAGIC_PE32 = 0x10B
DIR_LOAD_CONFIG = 10
FIRST_WORD = 0x2C


def load_config(d):
    if d[:2] != b"MZ" or len(d) < 0x100:
        return None
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return None
    nsections, = struct.unpack_from("<H", d, pe + 6)
    opt_size, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    if struct.unpack_from("<H", d, opt)[0] != MAGIC_PE32:
        return False
    if struct.unpack_from("<I", d, opt + 92)[0] <= DIR_LOAD_CONFIG:
        return 0
    rva, _ = struct.unpack_from("<II", d, opt + 96 + 8 * DIR_LOAD_CONFIG)
    if not rva:
        return 0
    for i in range(nsections):
        _, vsize, va, rsize, rptr, *_ = struct.unpack_from("<8sIIIII", d, opt + opt_size + 40 * i)
        if va <= rva < va + max(vsize, rsize):
            return rptr + rva - va
    return 0


def main(roots):
    images = configs = 0
    hits = []
    for root in roots:
        for dirpath, _, names in os.walk(root):
            for name in sorted(names):
                path = os.path.join(dirpath, name)
                try:
                    with open(path, "rb") as f:
                        d = f.read()
                    off = load_config(d)
                except (OSError, struct.error):
                    continue
                if off is None or off is False:
                    continue
                images += 1
                if not off:
                    continue
                size, = struct.unpack_from("<I", d, off)
                if size < 0x34:
                    continue
                configs += 1
                heap, affinity = struct.unpack_from("<II", d, off + FIRST_WORD)
                if heap or affinity:
                    hits.append((path, heap, affinity))
    print("pe32 images %d with a load configuration %d setting either word %d" % (images, configs, len(hits)))
    for path, heap, affinity in hits:
        print("%s heap %#x affinity %#x" % (path, heap, affinity))


main(sys.argv[1:])

#!/usr/bin/env python3
"""write small PE images that carry the structures no local image has: bound imports,
ARM64EC and CHPE metadata with their code maps, a CLR header, an import address table and
a certificate.

usage: python3 -I tools/coff/synth.py <fresh directory>

the images give the readobj lane inputs for those structures, so every value is arbitrary
but in range. nothing here runs in CI.
"""
import os
import struct
import sys

BASE64 = 0x180000000
BASE32 = 0x10000000
HEADERS = 0x400
TEXT_RVA, TEXT_RAW, TEXT_SIZE = 0x1000, 0x400, 0x200
DATA_RVA, DATA_RAW, DATA_SIZE = 0x2000, 0x600, 0x800
CHPE_OFFSET = {False: 0xC8, True: 0x7C}
DIR_SECURITY, DIR_LOAD_CONFIG, DIR_BOUND_IMPORT, DIR_IAT, DIR_CLR = 4, 10, 11, 12, 14


def pad(b, n):
    return b + bytes(n - len(b))


def section(name, rva, raw, flags):
    return struct.pack("<8sIIIIIIHHI", name, DATA_SIZE if name == b".rdata" else TEXT_SIZE, rva, DATA_SIZE if name == b".rdata" else TEXT_SIZE, raw, 0, 0, 0, 0, flags)


def image(machine, pe32, dirs, data, head=b"", head_at=0, tail=b""):
    """headers, a .text of int3 and a .rdata holding `data`. `head` is written at `head_at` inside the headers, `tail` follows the last section"""
    d = bytearray(16 * 8)
    for i, (rva, size) in dirs.items():
        struct.pack_into("<II", d, 8 * i, rva, size)
    if pe32:
        opt = struct.pack("<HBBIIIIIIIIIHHHHHHIIIIHHIIIIII", 0x10B, 14, 0, TEXT_SIZE, DATA_SIZE, 0, TEXT_RVA, TEXT_RVA, DATA_RVA,
                          BASE32, 0x1000, 0x200, 6, 0, 0, 0, 6, 0, 0, 0x3000, HEADERS, 0, 3, 0x8140,
                          0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    else:
        opt = struct.pack("<HBBIIIIIQIIHHHHHHIIIIHHQQQQII", 0x20B, 14, 0, TEXT_SIZE, DATA_SIZE, 0, TEXT_RVA, TEXT_RVA,
                          BASE64, 0x1000, 0x200, 6, 0, 0, 0, 6, 0, 0, 0x3000, HEADERS, 0, 3, 0x8160,
                          0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    opt += bytes(d)
    fh = struct.pack("<HHIIIHH", machine, 2, 0x5F000000, 0, 0, len(opt), 0x0102 if pe32 else 0x2022)
    dos = pad(b"MZ" + bytes(0x3A) + struct.pack("<I", 0x80), 0x80)
    hdr = bytearray(pad(dos + b"PE\0\0" + fh + opt + section(b".text", TEXT_RVA, TEXT_RAW, 0x60000020) + section(b".rdata", DATA_RVA, DATA_RAW, 0x40000040), HEADERS))
    hdr[head_at:head_at + len(head)] = head
    return bytes(hdr) + b"\xcc" * TEXT_SIZE + pad(bytes(data), DATA_SIZE) + tail


class Data:
    """the .rdata contents, written by offset"""

    def __init__(self):
        self.b = bytearray(DATA_SIZE)

    def put(self, off, raw):
        self.b[off:off + len(raw)] = raw
        return DATA_RVA + off


def load_config(pe32, chpe_va):
    size = 0xA0 if pe32 else 0x140
    lc = bytearray(size)
    struct.pack_into("<I", lc, 0, size)
    if pe32:
        struct.pack_into("<I", lc, CHPE_OFFSET[True], chpe_va)
    else:
        struct.pack_into("<Q", lc, CHPE_OFFSET[False], chpe_va)
    return bytes(lc)


def arm64ec(machine):
    d = Data()
    cm = d.put(0x300, struct.pack("<8I", TEXT_RVA | 1, 0x80, TEXT_RVA + 0x80, 0x40, (TEXT_RVA + 0xC0) | 2, 0x20, (TEXT_RVA + 0xE0) | 3, 0x10))
    er = d.put(0x340, struct.pack("<6I", TEXT_RVA, TEXT_RVA + 0x10, TEXT_RVA + 0x20, TEXT_RVA + 0x30, TEXT_RVA + 0x40, TEXT_RVA + 0x50))
    rd = d.put(0x380, struct.pack("<2I", TEXT_RVA + 0x60, TEXT_RVA + 0x70))
    md = d.put(0x200, struct.pack("<29I", 1, cm, 4, er, rd, 0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x2400, 2, 1,
                                   0x1007, 0x1008, 0x2410, 0x20, 0x1009, 0x2420, 1, 2, 3, 4, 5, 6, 7, 8, 9))
    lc = load_config(False, BASE64 + md)
    d.put(0, lc)
    return image(machine, False, {DIR_LOAD_CONFIG: (DATA_RVA, len(lc))}, d.b)


def chpe_x86():
    d = Data()
    cr = d.put(0x300, struct.pack("<4I", TEXT_RVA | 1, 0x80, TEXT_RVA + 0x80, 0x100))
    md = d.put(0x200, struct.pack("<16I", 4, cr, 2, 0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007, 0x2400, 0x1008, 0, 0, 0, 0))
    lc = load_config(True, BASE32 + md)
    d.put(0, lc)
    return image(0x14C, True, {DIR_LOAD_CONFIG: (DATA_RVA, len(lc))}, d.b)


def managed():
    """bound imports in the header slack, an import address table, a CLR header and a certificate"""
    d = Data()
    iat = d.put(0x100, struct.pack("<3Q", 0x2200, 0x2210, 0))
    clr = d.put(0x200, struct.pack("<IHHIIIIIIIIIIIIIIII", 72, 2, 5, DATA_RVA + 0x300, 0x40, 1, 0x1000, DATA_RVA + 0x340, 8,
                                    DATA_RVA + 0x348, 8, 0, 0, 0, 0, 0, 0, 0, 0))
    cert_at = HEADERS + TEXT_SIZE + DATA_SIZE
    cert = struct.pack("<IHH", 16, 0x200, 2) + bytes(range(8))
    bound = struct.pack("<IHH", 0x5F000001, 24, 1) + struct.pack("<IHH", 0x5F000002, 37, 0) + bytes(8) + b"kernel32.dll\0" + b"ntdll.dll\0"
    bound_at = 0x200
    return image(0x8664, False, {DIR_SECURITY: (cert_at, len(cert)), DIR_BOUND_IMPORT: (bound_at, len(bound)), DIR_IAT: (iat, 24), DIR_CLR: (clr, 72)},
                 d.b, head=bound, head_at=bound_at, tail=cert)


def main():
    if len(sys.argv) != 2 or os.path.exists(sys.argv[1]):
        sys.exit("usage: python3 -I tools/coff/synth.py <fresh directory>")
    os.makedirs(sys.argv[1])
    for name, data in (("arm64ec.exe", arm64ec(0x8664)), ("arm64.exe", arm64ec(0xAA64)), ("chpe-x86.exe", chpe_x86()), ("managed.exe", managed())):
        with open(os.path.join(sys.argv[1], name), "wb") as f:
            f.write(data)


main()

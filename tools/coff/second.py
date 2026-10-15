#!/usr/bin/env python3
"""check the PE fields mink dump prints under winnt.h names, which llvm-readobj
does not print, against a second reader.

usage: python3 -I tools/coff/second.py <mink> < list

<list> holds one image path per line. for each image the script reads, with
pefile and its own reading of the layouts winnt.h and ECMA-335 give, the fields
below, and compares each with what `mink dump` prints:
- the load configuration's code integrity fields and its tail after
  GuardEHContinuationCount, as pefile's IMAGE_LOAD_CONFIG_DIRECTORY rows name them
- the certificate table's WIN_CERTIFICATE headers, walked at the file offset the
  security directory states, each padded to eight bytes
- the import address table's slots, the words of the IAT directory
- the CLR runtime header, IMAGE_COR20_HEADER of ECMA-335 II.25.3.3
a field the second reader has and mink does not print, or prints with another
value, is a difference. it prints the structures checked and how many images held
each, then each difference, and exits 1 on any. nothing here runs in CI.
"""
import re
import struct
import subprocess
import sys

import pefile

FIELD = re.compile(r"^\s*([^:{}\[\]]+?):\s*(.*?)\s*$")
OPEN = re.compile(r"^\s*(.*?)\s*[{\[](?:\s*(\(.*\)))?\s*$")
CLOSE = re.compile(r"^\s*[}\]]\s*$")

LOAD_CONFIG = [
    "CodeIntegrityFlags", "CodeIntegrityCatalog", "CodeIntegrityCatalogOffset", "CodeIntegrityReserved",
    "GuardXFGCheckFunctionPointer", "GuardXFGDispatchFunctionPointer", "GuardXFGTableDispatchFunctionPointer",
    "CastGuardOsDeterminedFailureMode", "GuardMemcpyFunctionPointer",
]
COR20_DIRECTORIES = ["MetaData", "Resources", "StrongNameSignature", "CodeManagerTable", "VTableFixups",
                     "ExportAddressTableJumps", "ManagedNativeHeader"]


def parse(text):
    """the dump's fields by path, each record qualified by its occurrence"""
    fields = {}
    stack = [("", {})]
    for line in text.splitlines():
        if CLOSE.match(line):
            if len(stack) > 1:
                stack.pop()
            continue
        m = OPEN.match(line)
        if m and not FIELD.match(line):
            seen = stack[-1][1]
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
            stack.append((f"{m.group(1)}#{seen[m.group(1)]}", {}))
            continue
        m = FIELD.match(line)
        if m:
            seen = stack[-1][1]
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
            fields["/".join(p for p, _ in stack if p) + f"/{m.group(1)}#{seen[m.group(1)]}"] = m.group(2)
    return fields


def number(s):
    m = re.match(r"^(0x[0-9a-fA-F]+|\d+)", s)
    return int(m.group(1), 0) if m else None


def load_config(pe, want):
    if not hasattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG"):
        return
    s = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
    keys = [k[0] for k in s.__keys__]
    for name in LOAD_CONFIG:
        if name not in keys:
            continue
        # a field that ends past the structure's stated size is not in the file
        i = keys.index(name)
        end = s.get_field_relative_offset(keys[i + 1]) if i + 1 < len(keys) else s.sizeof()
        if end > s.Size:
            continue
        want[f"LoadConfig#1/{name}#1"] = getattr(s, name)


def certificates(pe, data, want):
    d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]]
    if not d.VirtualAddress or not d.Size or d.VirtualAddress + d.Size > len(data):
        return False
    at, end, k = d.VirtualAddress, d.VirtualAddress + d.Size, 0
    while at + 8 <= end:
        length, revision, kind = struct.unpack_from("<IHH", data, at)
        k += 1
        want[f"CertificateTable#1/Certificate#{k}/Length#1"] = length
        want[f"CertificateTable#1/Certificate#{k}/Revision#1"] = revision
        want[f"CertificateTable#1/Certificate#{k}/CertificateType#1"] = kind
        if length < 8:
            break
        at += (length + 7) & ~7
    return k > 0


def iat(pe, want):
    d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IAT"]]
    if not d.VirtualAddress or not d.Size:
        return False
    width = 8 if pe.OPTIONAL_HEADER.Magic == 0x20b else 4
    raw = pe.get_data(d.VirtualAddress, d.Size)
    fmt = "<Q" if width == 8 else "<I"
    for k in range(len(raw) // width):
        want[f"ImportAddressTable#1/Address#{k + 1}"] = struct.unpack_from(fmt, raw, k * width)[0]
    return True


def cor20(pe, want):
    d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR"]]
    if not d.VirtualAddress or d.Size < 0x48:
        return False
    raw = pe.get_data(d.VirtualAddress, 0x48)
    cb, major, minor = struct.unpack_from("<IHH", raw, 0)
    base = "CLRRuntimeHeader#1"
    want[f"{base}/cb#1"] = cb
    want[f"{base}/MajorRuntimeVersion#1"] = major
    want[f"{base}/MinorRuntimeVersion#1"] = minor
    va, size = struct.unpack_from("<II", raw, 8)
    want[f"{base}/MetaData#1/VirtualAddress#1"] = va
    want[f"{base}/MetaData#1/Size#1"] = size
    flags, entry = struct.unpack_from("<II", raw, 16)
    want[f"{base}/Flags#1"] = flags
    want[f"{base}/EntryPoint#1"] = entry
    for k, name in enumerate(COR20_DIRECTORIES[1:]):
        va, size = struct.unpack_from("<II", raw, 24 + 8 * k)
        want[f"{base}/{name}#1/VirtualAddress#1"] = va
        want[f"{base}/{name}#1/Size#1"] = size
    return True


def main():
    mink = sys.argv[1]
    held = {"load configuration code integrity and tail": 0, "certificates": 0, "import address table": 0,
            "CLR runtime header": 0}
    bad = 0
    files = 0
    for path in sys.stdin.read().splitlines():
        if not path:
            continue
        r = subprocess.run([mink, "dump", path], capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            continue
        try:
            pe = pefile.PE(path)
        except pefile.PEFormatError:
            continue
        files += 1
        data = pe.__data__
        want = {}
        load_config(pe, want)
        if any(k.startswith("LoadConfig#1/") for k in want):
            held["load configuration code integrity and tail"] += 1
        if certificates(pe, data, want):
            held["certificates"] += 1
        if iat(pe, want):
            held["import address table"] += 1
        if cor20(pe, want):
            held["CLR runtime header"] += 1
        pe.close()
        ours = parse(r.stdout)
        for key, value in want.items():
            got = ours.get(key)
            if got is None or number(got) != value:
                print(f"  {path}: {key}: mink {got!r}, second reader {value:#x}")
                bad += 1
    print(f"{files} images read by both")
    for name, n in held.items():
        print(f"  {name}: {n} images")
    print(f"{bad} differ")
    sys.exit(1 if bad else 0)


main()

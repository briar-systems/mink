#!/usr/bin/env python3
"""compare mink's Mach-O executables with ld64.lld's image of the same objects.

usage: machoexec.py --mink <mink> --source <dir> --work <dir>

the input set is every .c file of <dir>, compiled by clang for arm64 and x86_64
with -O1, and x86_64 with -fno-asynchronous-unwind-tables as well, since clang
writes __eh_frame for x86_64 beside its compact unwind and mink refuses an
__eh_frame until #412. each object links twice: for macOS 11.0,
whose loader the image rebases through rebase opcodes, and for macOS 12.0,
through chained fixups. the oracle is ld64.lld, run as
  ld64.lld -arch <arch> -platform_version macos <v> <v> [-fixup_chains]
           -ignore_optimization_hints -e _main -o <image> <object>
and mink as
  mink link <object> -o <image> --kind pie --format macho --arch <arch>
            --system darwin --env macos --system-version <v> --sdk-version <v>
            --entry _main
each pair is compared through
  llvm-objdump --macho --private-headers
  llvm-readobj --macho-segment --macho-dysymtab --macho-version-min
               --macho-data-in-code --macho-indirect-symbols
  llvm-objdump --macho --rebase, --chained-fixups and --function-starts
the bytes of every __DATA section, and the code as llvm-objdump -d prints it,
each place-relative field read as the address it reaches. a field is left out of the comparison
only for a reason EXCLUDED states: one the load command measure or the code
signature decides, one that names the image or its linker, and the known
differences, each an open issue.

each object also links with every UNSIGNED relocation of its __DATA,__data made
a local one against R_ABS, its field holding 0x1234. ld64.lld 23.1.1 aborts on
such a relocation, so mink's image is judged by the value the relocation has at
S = 0, the field's addend, and by holding no rebase for it.

exit 0 when every pair agrees, 1 on any difference.
"""
import argparse
import os
import re
import struct
import subprocess
import sys

ARCHES = [("arm64", "aarch64"), ("x86_64", "x86_64")]
MODES = [("opcodes", "11.0", []), ("chained", "12.0", ["-fixup_chains"])]
CFLAGS = {"arm64": ["-O1"], "x86_64": ["-O1", "-fno-asynchronous-unwind-tables"]}
READOBJ = ["--macho-segment", "--macho-dysymtab", "--macho-version-min", "--macho-data-in-code", "--macho-indirect-symbols"]
ABS_VALUE = 0x1234

MEASURE = "decided by the load command measure"
SIGNATURE = "decided by the code signature, which ld64.lld writes and mink does not until #371"
NAMED = "names the image or the linker that wrote it"
EXPORTS = "the export trie and __mh_execute_header, a known difference, #390"
LIB64 = "CPU_SUBTYPE_LIB64 on an x86_64 executable, a known difference, #391"

# (command or record, field) -> why it is left out. a command of "*" is any
EXCLUDED = {
    ("header", "sizeofcmds"): MEASURE,
    ("header", "ncmds"): SIGNATURE,
    ("header", "caps"): LIB64,
    ("*", "cmdsize"): NAMED,
    ("section __TEXT", "addr"): MEASURE,
    ("section __TEXT", "offset"): MEASURE,
    ("LC_MAIN", "entryoff"): MEASURE,
    ("segment __LINKEDIT", "vmsize"): SIGNATURE,
    ("segment __LINKEDIT", "filesize"): SIGNATURE,
    ("*", "dataoff"): SIGNATURE,
    ("*", "rebase_off"): SIGNATURE,
    ("LC_SYMTAB", "symoff"): SIGNATURE,
    ("LC_SYMTAB", "stroff"): SIGNATURE,
    ("LC_SYMTAB", "nsyms"): EXPORTS,
    ("LC_SYMTAB", "strsize"): EXPORTS,
    ("LC_DYSYMTAB", "nextdefsym"): EXPORTS,
    ("LC_DYSYMTAB", "iundefsym"): EXPORTS,
    ("LC_DYLD_INFO_ONLY", "export_off"): EXPORTS,
    ("LC_DYLD_INFO_ONLY", "export_size"): EXPORTS,
    ("LC_UUID", "uuid"): NAMED,
    ("LC_BUILD_VERSION", "ntools"): NAMED,
    ("LC_BUILD_VERSION", "tool"): NAMED,
    ("LC_BUILD_VERSION", "version"): NAMED,
}

# whole load commands only ld64.lld writes
ONLY_LLD = {"LC_CODE_SIGNATURE": SIGNATURE, "LC_DYLD_EXPORTS_TRIE": EXPORTS}

# readobj records and fields, the same reasons
READOBJ_EXCLUDED = {
    ("Segment __LINKEDIT", "vmsize"): SIGNATURE,
    ("Segment __LINKEDIT", "filesize"): SIGNATURE,
    ("Section __TEXT", "Address"): MEASURE,
    ("Section __TEXT", "Offset"): MEASURE,
    ("Dysymtab", "nextdefsym"): EXPORTS,
    ("Dysymtab", "iundefsym"): EXPORTS,
    ("DataInCode", "Data offset"): SIGNATURE,
    ("MinVersion", "Size"): NAMED,
}


def run(argv, log=None):
    p = subprocess.run(argv, capture_output=True, text=True)
    if log is not None:
        with open(log, "w") as f:
            f.write(p.stdout + p.stderr)
    return p


def commands(image):
    """the header and each load command of `image` as llvm-objdump prints them, a
    section a record of its own named by its segment"""
    out = run(["llvm-objdump", "--macho", "--private-headers", image]).stdout.splitlines()
    blocks = []
    cur = None
    header = None
    for line in out:
        s = line.strip()
        if s.startswith("magic "):
            header = s.split()
            continue
        if header is not None and cur is None and s.startswith("MH_"):
            blocks.append(("header", dict(zip(header, s.split()))))
            continue
        if s.startswith("Load command"):
            cur = None
            continue
        if s == "Section":
            cur = ["section", {}]
            blocks.append(cur)
            continue
        m = re.match(r"^(\S+)\s+(.*)$", s)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if k == "cmd":
            cur = [v, {}]
            blocks.append(cur)
            continue
        if cur is None:
            continue
        cur[1].setdefault(k, v)
        if cur[0] == "section" and k == "segname":
            cur[0] = "section " + v
        if cur[0] == "LC_SEGMENT_64" and k == "segname":
            cur[0] = "segment " + v
    return [(b[0], b[1]) for b in blocks]


def excluded(name, key, table):
    for k in ((name, key), (name.split(" ")[0], key), ("*", key)):
        if k in table:
            return table[k]
    return None


def compare_commands(mine, theirs):
    diffs = []
    theirs = [b for b in theirs if b[0] not in ONLY_LLD]
    names_m = [b[0] for b in mine]
    names_t = [b[0] for b in theirs]
    if names_m != names_t:
        return ["load commands: mink %s, ld64.lld %s" % (names_m, names_t)]
    for (name, fm), (_, ft) in zip(mine, theirs):
        for k in sorted(set(fm) | set(ft)):
            if excluded(name, k, EXCLUDED):
                continue
            if fm.get(k) != ft.get(k):
                diffs.append("%s %s: mink %s, ld64.lld %s" % (name, k, fm.get(k), ft.get(k)))
    return diffs


def readobj(image):
    """the fields llvm-readobj prints, each keyed by its record and the record's
    segment or section name"""
    out = run(["llvm-readobj"] + READOBJ + [image]).stdout.splitlines()
    fields = []
    stack = []
    for line in out:
        s = line.strip()
        if s.endswith("{"):
            stack.append([s[:-1].strip(), ""])
            continue
        if s == "}":
            if stack:
                stack.pop()
            continue
        m = re.match(r"^([^:]+):\s*(.*)$", s)
        if not m or not stack:
            continue
        k, v = m.group(1), m.group(2)
        if k in ("Name", "Segment") and not stack[-1][1]:
            stack[-1][1] = v.split()[0]
        fields.append((stack[-1][0], stack[-1][1], k, v))
    return fields


def compare_readobj(mine, theirs):
    def keep(fs):
        out = []
        for rec, owner, k, v in fs:
            name = (rec + " " + owner).strip()
            if excluded(name, k, READOBJ_EXCLUDED) or excluded(rec, k, READOBJ_EXCLUDED):
                continue
            if k == "File":
                continue
            out.append((name, k, v))
        return out

    m, t = keep(mine), keep(theirs)
    if len(m) != len(t):
        return ["llvm-readobj prints %d fields of mink's image and %d of ld64.lld's" % (len(m), len(t))]
    return ["llvm-readobj %s %s: mink %s, ld64.lld %s" % (a[0], a[1], a[2], b[2]) for a, b in zip(m, t) if a != b]


def listing(flag, image):
    lines = run(["llvm-objdump", "--macho", flag, image]).stdout.splitlines()
    return [l for l in lines[1:] if l.strip()]


def function_starts(image, blocks):
    text = [b[1] for b in blocks if b[0] == "section __TEXT" and b[1].get("sectname") == "__text"]
    base = int(text[0]["addr"], 16) if text else 0
    out = []
    for l in listing("--function-starts", image):
        w = l.split()
        if w and re.match(r"^[0-9a-f]+$", w[0]):
            out.append(int(w[0], 16) - base)
    return out


def code(image):
    """the instructions of `image`, each with the address it reaches rather than
    the place-relative field, since the load commands decide where code starts"""
    out = []
    for l in run(["llvm-objdump", "-d", "--no-show-raw-insn", image]).stdout.splitlines():
        m = re.match(r"^\s*[0-9a-f]+:\s*(.*)$", l)
        if not m:
            continue
        insn = re.sub(r"-?0x[0-9a-f]+\(%rip\)", "(%rip)", m.group(1))
        out.append(" ".join(insn.split()))
    return out


def data_bytes(image, blocks):
    raw = open(image, "rb").read()
    out = {}
    for name, f in blocks:
        if name.startswith("section __DATA") and f.get("type") != "S_ZEROFILL":
            off, size = int(f["offset"]), int(f["size"], 16)
            out[f["sectname"]] = raw[off:off + size]
    return out


def r_abs(src, dst):
    """`src` with every UNSIGNED relocation of __DATA,__data made local against
    R_ABS, its field holding ABS_VALUE, written to `dst`. the offsets of the
    pointers it rewrote"""
    d = bytearray(open(src, "rb").read())
    ncmds = struct.unpack_from("<I", d, 16)[0]
    at, sites = 32, []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", d, at)
        if cmd == 0x19:
            for k in range(struct.unpack_from("<I", d, at + 64)[0]):
                s = at + 72 + 80 * k
                if d[s:s + 16].rstrip(b"\0") != b"__data":
                    continue
                off, _, reloff, nreloc = struct.unpack_from("<IIII", d, s + 48)
                for r in range(nreloc):
                    ra = reloff + 8 * r
                    addr, info = struct.unpack_from("<iI", d, ra)
                    if info >> 28 != 0:
                        continue
                    struct.pack_into("<iI", d, ra, addr, info & 0xf7000000 & ~0x00ffffff)
                    struct.pack_into("<Q", d, off + addr, ABS_VALUE)
                    sites.append(addr)
        at += size
    open(dst, "wb").write(d)
    return sites


def link_mink(a, obj, image, arch, version):
    return run([a.mink, "link", obj, "-o", image, "--kind", "pie", "--format", "macho", "--arch", arch, "--system", "darwin",
                "--env", "macos", "--system-version", version, "--sdk-version", version, "--entry", "_main"], image + ".log")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mink", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    os.makedirs(a.work, exist_ok=True)
    print("machoexec: excluded fields:")
    for (c, k), why in sorted(EXCLUDED.items()):
        print("  %s %s: %s" % (c, k, why))
    for c, why in sorted(ONLY_LLD.items()):
        print("  %s: %s" % (c, why))
    failed = 0
    sources = sorted(f for f in os.listdir(a.source) if f.endswith(".c"))
    for src in sources:
        for darwin, arch in ARCHES:
            for mode, version, extra in MODES:
                label = "%s %s %s" % (src, darwin, mode)
                obj = os.path.join(a.work, "%s-%s-%s.o" % (src, darwin, mode))
                if run(["clang", "--target=%s-apple-macos%s" % (darwin, version)] + CFLAGS[darwin] + ["-c", os.path.join(a.source, src), "-o", obj]).returncode:
                    print("FAIL  %s: clang does not compile it" % label)
                    failed += 1
                    continue
                theirs, mine = obj + ".lld", obj + ".mink"
                lld = run(["ld64.lld", "-arch", darwin, "-platform_version", "macos", version, version] + extra
                          + ["-ignore_optimization_hints", "-e", "_main", "-o", theirs, obj], theirs + ".log")
                if lld.returncode:
                    print("FAIL  %s: ld64.lld refuses it, see %s.log" % (label, theirs))
                    failed += 1
                    continue
                if link_mink(a, obj, mine, arch, version).returncode:
                    print("FAIL  %s: mink refuses it: %s" % (label, open(mine + ".log").read().strip()))
                    failed += 1
                    continue
                cm, ct = commands(mine), commands(theirs)
                diffs = compare_commands(cm, ct)
                diffs += compare_readobj(readobj(mine), readobj(theirs))
                for flag in ("--rebase", "--chained-fixups"):
                    if listing(flag, mine) != listing(flag, theirs):
                        diffs.append("llvm-objdump %s differs" % flag)
                if code(mine) != code(theirs):
                    diffs.append("the code reaches different addresses")
                if function_starts(mine, cm) != function_starts(theirs, ct):
                    diffs.append("function starts differ from the start of __text")
                if data_bytes(mine, cm) != data_bytes(theirs, ct):
                    diffs.append("the bytes of a __DATA section differ")
                if diffs:
                    failed += 1
                    print("FAIL  %s:" % label)
                    for d in diffs:
                        print("        " + d)
                else:
                    print("agree %s" % label)
                absobj = obj + ".abs.o"
                sites = r_abs(obj, absobj)
                absimg = absobj + ".mink"
                if not sites:
                    print("FAIL  %s R_ABS: the object holds no pointer to rewrite" % label)
                    failed += 1
                    continue
                if link_mink(a, absobj, absimg, arch, version).returncode:
                    print("FAIL  %s R_ABS: mink refuses it: %s" % (label, open(absimg + ".log").read().strip()))
                    failed += 1
                    continue
                blocks = commands(absimg)
                data = data_bytes(absimg, blocks).get("__data", b"")
                words = [struct.unpack_from("<Q", data, s)[0] for s in sites]
                rebased = [l for l in listing("--rebase", absimg) + listing("--chained-fixups", absimg) if "__data" in l or "page_start" in l]
                if any(w != ABS_VALUE for w in words) or rebased:
                    print("FAIL  %s R_ABS: words %s, rebases %s" % (label, [hex(w) for w in words], rebased))
                    failed += 1
                else:
                    print("agree %s R_ABS: S = 0 gives 0x%x, no rebase" % (label, ABS_VALUE))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

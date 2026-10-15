# compare the link-edit entries mink dump decodes of one thin Mach-O file
# with what llvm-objdump prints of the same file
#
# usage: python3 -I objdump.py <mink dump> <directory of llvm-objdump outputs>
#
# the directory holds one file per llvm-objdump option, written by
# objdump.sh: rebase, bind, lazy, weak, exports, starts, dic, unwind, chained.
# every rebase, bind, export, function start, data-in-code entry, chained
# fixup header field and import, and every part of the unwind info both tools
# decode is compared, and each difference is printed as one line. a blob mink
# holds raw is counted and named, never compared: the dump does not say which
# dyld info table a raw blob is, so while one is present an entry only
# llvm-objdump decodes of those tables is not a difference, and an entry only
# mink decodes always is. exit status is the number of differences, so 0 means
# the two agree on every decoded entry.
import os
import re
import sys


class Node:
    def __init__(self, name, parent=None):
        self.name = name
        self.fields = []
        self.children = []
        self.parent = parent

    def get(self, key, default=None):
        for k, v in self.fields:
            if k == key:
                return v
        return default

    def all(self, key):
        return [v for k, v in self.fields if k == key]

    def kids(self, name):
        return [c for c in self.children if c.name == name]


def parse_dump(path):
    root = Node("root")
    cur = root
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == "}":
                cur = cur.parent or root
            elif line.endswith(" {"):
                node = Node(line[:-2], cur)
                cur.children.append(node)
                cur = node
            elif ": " in line or line.endswith(":"):
                k, _, v = line.partition(":")
                cur.fields.append((k.strip(), v.strip()))
            else:
                cur.fields.append((line, ""))
    return root


def num(text):
    """the number a dump value starts with, hex or decimal, or None"""
    m = re.match(r"-?(0x[0-9a-fA-F]+|\d+)", text.strip())
    if not m:
        return None
    return int(m.group(0), 0)


def named(text):
    """the constant name before its number, as `REBASE_TYPE_POINTER (0x1)` has it"""
    return text.split(" (")[0].strip()


def read_lines(dir, name):
    path = os.path.join(dir, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f]


class Image:
    def __init__(self, root):
        self.segments = []
        self.sections = []
        self.libraries = []
        self.text_vmaddr = 0
        for seg in root.kids("Segment"):
            vm = num(seg.get("vmaddr", "0"))
            self.segments.append((seg.get("Name", ""), vm))
            if seg.get("Name", "") == "__TEXT":
                self.text_vmaddr = vm
        for secs in root.kids("Sections"):
            for s in secs.kids("Section"):
                self.sections.append((s.get("Segment", ""), s.get("Name", ""), num(s.get("Address", "0")), num(s.get("Size", "0")), s))
        for lc in root.kids("LoadCommand"):
            cmd = named(lc.get("Cmd", ""))
            if cmd in ("LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB", "LC_LAZY_LOAD_DYLIB"):
                for lib in lc.kids("Library"):
                    self.libraries.append(lib.get("Name", "").rsplit(" (", 1)[0])

    def section_of(self, address):
        for seg, name, addr, size, _ in self.sections:
            if addr <= address < addr + max(size, 1):
                return seg, name
        for seg, vm in reversed(sorted(self.segments, key=lambda s: s[1])):
            if address >= vm:
                return seg, ""
        return "", ""

    def dylib(self, ordinal):
        special = {0: "this-image", -1: "main-executable", -2: "flat-namespace", -3: "weak"}
        if ordinal in special:
            return special[ordinal]
        if 1 <= ordinal <= len(self.libraries):
            return short_name(self.libraries[ordinal - 1])
        return "ordinal %d" % ordinal


def short_name(path):
    """llvm's guess of a library's short name: the framework or the lib name
    without its extension and version"""
    parts = path.split("/")
    for i, p in enumerate(parts):
        if p.endswith(".framework") and i + 1 < len(parts):
            return parts[-1]
    base = parts[-1]
    for ext in (".dylib", ".so", ".bundle"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    base = re.sub(r"(\.[0-9]+)+$", "", base)
    return base


REBASE_TYPES = {"REBASE_TYPE_POINTER": "pointer", "REBASE_TYPE_TEXT_ABSOLUTE32": "text abs32", "REBASE_TYPE_TEXT_PCREL32": "text rel32"}
BIND_TYPES = {"BIND_TYPE_POINTER": "pointer", "BIND_TYPE_TEXT_ABSOLUTE32": "text abs32", "BIND_TYPE_TEXT_PCREL32": "text rel32"}


def report(diffs, what, mine, theirs, partial=False):
    """every entry one side has and the other lacks. with `partial`, mink may
    hold one of the tables raw, so only its own extra entries count"""
    for e in sorted(set(mine) - set(theirs)):
        diffs.append("%s: only mink: %s" % (what, e))
    if partial:
        return
    for e in sorted(set(theirs) - set(mine)):
        diffs.append("%s: only llvm-objdump: %s" % (what, e))


def table_rows(lines, header):
    """the rows after the line starting with `header`, up to a blank line"""
    rows = []
    on = False
    for l in lines:
        if l.startswith(header):
            on = True
            continue
        if on:
            if not l.strip():
                break
            if l.startswith("segment ") or l.startswith("offset "):
                continue
            rows.append(l.split())
    return rows


def compare(dump, dir):
    root = parse_dump(dump)
    img = Image(root)
    diffs = []
    raw = []
    linkedit = root.kids("LinkEdit")
    le = linkedit[0] if linkedit else Node("LinkEdit")
    for k, v in le.fields:
        if k == "Reason":
            raw.append(v)

    # rebases
    mine = []
    for block in le.kids("RebaseEntries"):
        for e in block.kids("RebaseEntry"):
            seg = num(e.get("Segment", "0"))
            addr = img.segments[seg][1] + num(e.get("Offset", "0")) if seg < len(img.segments) else num(e.get("Offset", "0"))
            s, n = img.section_of(addr)
            mine.append((s, n, "0x%08X" % addr, REBASE_TYPES.get(named(e.get("Type", "")), named(e.get("Type", "")))))
    theirs = []
    for r in table_rows(read_lines(dir, "rebase"), "Rebase table:"):
        if len(r) >= 4:
            theirs.append((r[0], r[1], "0x%08X" % int(r[2], 16), " ".join(r[3:])))
    partial = len(raw) > 0
    if le.kids("RebaseEntries"):
        report(diffs, "rebase", mine, theirs, partial)

    # binds of every flavour as one set, lazy binds carrying no type or addend
    mine = []
    for block in le.kids("BindEntries"):
        for e in block.kids("BindEntry"):
            seg = num(e.get("Segment", "0"))
            addr = img.segments[seg][1] + num(e.get("Offset", "0")) if seg < len(img.segments) else num(e.get("Offset", "0"))
            s, n = img.section_of(addr)
            ordinal = int(e.get("Ordinal", "0"))
            name = e.get("Name", "").rsplit(" (", 1)[0]
            mine.append((s, n, "0x%08X" % addr, name))
    theirs = []
    for r in table_rows(read_lines(dir, "bind"), "Bind table:"):
        if len(r) >= 7:
            theirs.append((r[0], r[1], "0x%08X" % int(r[2], 16), r[6]))
    for r in table_rows(read_lines(dir, "lazy"), "Lazy bind table:"):
        if len(r) >= 5:
            theirs.append((r[0], r[1], "0x%08X" % int(r[2], 16), r[4]))
    for r in table_rows(read_lines(dir, "weak"), "Weak bind table:"):
        if len(r) >= 6 and r[3] != "strong":
            theirs.append((r[0], r[1], "0x%08X" % int(r[2], 16), r[5]))
    if le.kids("BindEntries"):
        report(diffs, "bind", mine, theirs, partial)

    # exports: name, address and attributes
    mine = []
    for block in le.kids("ExportEntries"):
        for e in block.kids("ExportEntry"):
            flags = num(e.get("Flags", "0"))
            attrs = []
            kind = flags & 3
            if kind == 1:
                attrs.append("per-thread")
            if kind == 2:
                attrs.append("absolute")
            if flags & 4:
                attrs.append("weak_def")
            if flags & 8:
                attrs.append("re-export")
            if flags & 16:
                attrs.append("resolver")
            # the trie states an offset from the mach header, which llvm-objdump
            # prints as an address in the image
            addr = "" if flags & 8 else "0x%08X" % (img.text_vmaddr + num(e.get("Address", "0")))
            mine.append((e.get("Name", ""), addr, " ".join(sorted(attrs))))
    theirs = []
    for l in read_lines(dir, "exports"):
        m = re.match(r"^(0x[0-9A-Fa-f]+)?\s*(\[re-export\])?\s*(\S+)(.*)$", l)
        if not m or l.startswith("Exports trie") or l.endswith(":") or not l.strip():
            continue
        if m.group(1) is None and m.group(2) is None:
            continue
        attrs = re.findall(r"\[([a-z_-]+)", l)
        attrs = [a for a in attrs if a in ("per-thread", "absolute", "weak_def", "re-export", "resolver")]
        addr = "0x%08X" % int(m.group(1), 16) if m.group(1) else ""
        theirs.append((m.group(3), addr, " ".join(sorted(attrs))))
    if le.kids("ExportEntries"):
        report(diffs, "export", mine, theirs, partial)

    # function starts, as addresses
    mine = []
    for block in le.kids("FunctionStarts"):
        for v in block.all("FunctionStart"):
            mine.append("0x%X" % (img.text_vmaddr + num(v)))
    theirs = []
    for l in read_lines(dir, "starts"):
        if re.match(r"^[0-9a-f]{16}$", l.strip()):
            theirs.append("0x%X" % int(l, 16))
    if le.kids("FunctionStarts"):
        report(diffs, "function start", mine, theirs)

    # data in code
    mine = []
    for block in le.kids("DataInCode"):
        for e in block.kids("Entry"):
            kind = named(e.get("Kind", "")).replace("DICE_KIND_", "")
            mine.append(("0x%016X" % num(e.get("Offset", "0")), str(num(e.get("Length", "0"))), kind))
    theirs = []
    for r in table_rows(read_lines(dir, "dic"), "Data in code table"):
        if len(r) >= 3:
            theirs.append(("0x%016X" % int(r[0], 16), r[1], r[2]))
    if le.kids("DataInCode"):
        report(diffs, "data in code", mine, theirs)

    # chained fixups: the header and the imports
    for block in le.kids("ChainedFixups"):
        lines = read_lines(dir, "chained")
        fields = {"fixups_version": "FixupsVersion", "starts_offset": "StartsOffset", "imports_offset": "ImportsOffset",
                  "symbols_offset": "SymbolsOffset", "imports_count": "ImportsCount", "imports_format": "ImportsFormat",
                  "symbols_format": "SymbolsFormat", "seg_count": "SegmentCount"}
        theirs_hdr = {}
        for l in lines:
            m = re.match(r"^\s*(\w+)\s*=\s*(\d+)", l)
            if m and m.group(1) in fields:
                theirs_hdr[fields[m.group(1)]] = int(m.group(2))
        for k in fields.values():
            mine_v = num(block.get(k, "0"))
            if k in theirs_hdr and theirs_hdr[k] != mine_v:
                diffs.append("chained %s: mink %d, llvm-objdump %d" % (k, mine_v, theirs_hdr[k]))
        fmt = num(block.get("ImportsFormat", "1"))
        width = 16 if fmt == 3 else 8
        mine = []
        for imports in block.kids("Imports"):
            for e in imports.kids("Import"):
                ordinal = num(e.get("Ordinal", "0"))
                if ordinal >= 1 << (width - 1):
                    ordinal -= 1 << width
                mine.append((ordinal, num(e.get("WeakImport", "0")), num(e.get("Name", "0"))))
        theirs = []
        cur = None
        for l in lines:
            if re.match(r"^dyld chained import\[\d+\]", l):
                cur = {}
                theirs.append(cur)
                continue
            m = re.match(r"^\s*(lib_ordinal|weak_import|name_offset)\s*=\s*(-?\d+)", l)
            if cur is not None and m:
                cur[m.group(1)] = int(m.group(2))
        theirs = [(c.get("lib_ordinal", 0), c.get("weak_import", 0), c.get("name_offset", 0)) for c in theirs]
        report(diffs, "chained import", mine, theirs)

    # the unwind info section
    for seg, name, addr, size, node in img.sections:
        for info in node.kids("UnwindInfo"):
            compare_unwind(diffs, info, read_lines(dir, "unwind"))
    return diffs, raw


def compare_unwind(diffs, info, lines):
    common = [num(v) for block in info.kids("CommonEncodings") for v in block.all("Encoding")]
    personalities = [num(v) for block in info.kids("Personalities") for v in block.all("Personality")]
    mine_common = ["0x%08X" % v for v in common]
    theirs_common = [("0x%08X" % int(m.group(1), 16)) for m in (re.match(r"^\s+encoding\[\d+\]: (0x[0-9a-f]+)", l) for l in lines) if m]
    if mine_common != theirs_common:
        diffs.append("unwind common encodings: mink %s, llvm-objdump %s" % (mine_common, theirs_common))
    theirs_pers = [("0x%08X" % int(m.group(1), 16)) for m in (re.match(r"^\s+personality\[\d+\]: (0x[0-9a-f]+)", l) for l in lines) if m]
    if ["0x%08X" % v for v in personalities] != theirs_pers:
        diffs.append("unwind personalities: mink %s, llvm-objdump %s" % (personalities, theirs_pers))
    mine = []
    for block in info.kids("IndexEntries"):
        for e in block.kids("Entry"):
            mine.append(("0x%08X" % num(e.get("Function", "0")), "0x%08X" % num(e.get("Page", "0")), "0x%08X" % num(e.get("LSDA", "0"))))
    theirs = []
    for l in lines:
        m = re.match(r"^\s+\[\d+\]: function offset=(0x[0-9a-f]+), 2nd level page offset=(0x[0-9a-f]+), LSDA offset=(0x[0-9a-f]+)", l)
        if m:
            theirs.append(tuple("0x%08X" % int(g, 16) for g in m.groups()))
    report(diffs, "unwind index", mine, theirs)
    mine = []
    for block in info.kids("LSDAs"):
        for e in block.kids("Entry"):
            mine.append(("0x%08X" % num(e.get("Function", "0")), "0x%08X" % num(e.get("LSDA", "0"))))
    theirs = []
    for l in lines:
        m = re.match(r"^\s+\[\d+\]: function offset=(0x[0-9a-f]+), LSDA offset=(0x[0-9a-f]+)$", l)
        if m:
            theirs.append(tuple("0x%08X" % int(g, 16) for g in m.groups()))
    report(diffs, "unwind lsda", mine, theirs)
    # second level pages: every function with its encoding
    mine = []
    bases = [num(e.get("Function", "0")) for block in info.kids("IndexEntries") for e in block.kids("Entry")]
    pages = [p for block in info.kids("Pages") for p in block.kids("Page")]
    for i, p in enumerate(pages):
        base = bases[i] if i < len(bases) else 0
        if p.get("Kind", "") == "regular":
            for block in p.kids("Entries"):
                for e in block.kids("Entry"):
                    mine.append(("0x%08X" % num(e.get("Function", "0")), "0x%08X" % num(e.get("Encoding", "0"))))
        else:
            own = [num(v) for block in p.kids("Encodings") for v in block.all("Word")]
            for block in p.kids("Entries"):
                for v in block.all("Word"):
                    w = num(v)
                    idx = w >> 24
                    enc = common[idx] if idx < len(common) else (own[idx - len(common)] if idx - len(common) < len(own) else 0)
                    mine.append(("0x%08X" % (base + (w & 0xFFFFFF)), "0x%08X" % enc))
    theirs = []
    for l in lines:
        m = re.match(r"^\s+\[\d+\]: function offset=(0x[0-9a-f]+), encoding(?:\[\d+\])?=(0x[0-9a-f]+)", l)
        if m:
            theirs.append(tuple("0x%08X" % int(g, 16) for g in m.groups()))
    report(diffs, "unwind entry", mine, theirs)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    diffs, raw = compare(sys.argv[1], sys.argv[2])
    for d in diffs:
        print(d)
    for r in raw:
        print("held raw: %s" % r)
    return min(len(diffs), 125)


if __name__ == "__main__":
    sys.exit(main())

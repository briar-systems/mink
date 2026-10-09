#!/usr/bin/env python3
# generate src/format/coff/model/tables.mach from tools/coff/tables.txt.
#
# run by hand from anywhere: python3 tools/coff/gen-tables.py, then
# mach fmt src/format/coff/model/tables.mach. the build never runs this, and the output
# is deterministic. the format of tables.txt is written at its head. every row is
# checked: a table opens before its rows, a name is defined once, a reference names a
# row an earlier table defines, a value fits in 64 bits, and every definition cites
# a source.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.join(HERE, "tables.txt")
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "src", "format", "coff", "model", "tables.mach")

MASK64 = (1 << 64) - 1
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def fail(lineno, msg):
    sys.exit("gen-tables: %s:%d: %s" % (TXT, lineno, msg))


def parse_value(text, lineno):
    m = re.match(r"^(-?)(0x[0-9A-Fa-f]+|\d+)$", text)
    if not m:
        fail(lineno, "bad value %r" % text)
    n = int(m.group(2), 0)
    if m.group(1):
        n = -n
    if n < -(1 << 63) or n > MASK64:
        fail(lineno, "value %r does not fit 64 bits" % text)
    return n & MASK64


def check_source(source, name, lineno):
    if not source.strip() or '"' in source or "\\" in source:
        fail(lineno, "bad source for %s" % name)
    return source.strip()


def parse():
    tables = []
    by_table = {}
    defs = {}
    blobs = []
    words = {}
    magics = []
    lookup = {}
    machines = []
    with open(TXT, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split(" ")
            if parts[0] == "table":
                head = line.split(" ", 2)
                if len(head) != 3 or not NAME.match(head[1]):
                    fail(lineno, "bad table line")
                if head[1] in by_table:
                    fail(lineno, "table %s declared twice" % head[1])
                tables.append((head[1], head[2]))
                by_table[head[1]] = []
                continue
            if parts[0] == "machine":
                if len(parts) < 5:
                    fail(lineno, "machine row needs code, relocation set, format and source")
                code, rel, fmt = parts[1], parts[2], parts[3]
                if ("MACHINE", code) not in lookup:
                    fail(lineno, "machine %s is not a row of MACHINE" % code)
                if rel != "-" and rel not in by_table:
                    fail(lineno, "machine %s names relocation set %s, which no table defines" % (code, rel))
                value = lookup[("MACHINE", code)]
                for earlier in machines:
                    if earlier[1] == value:
                        fail(lineno, "machine %s and machine %s share code 0x%x; each code takes one row"
                             % (earlier[0], code, value))
                source = check_source(" ".join(parts[4:]), code, lineno)
                machines.append((code, value, None if rel == "-" else rel, None if fmt == "-" else fmt, source))
                continue
            if parts[0] == "bytes":
                if len(parts) < 4:
                    fail(lineno, "bytes row needs a name, hex bytes and a source")
                name, hexed = parts[1], parts[2]
                source = check_source(" ".join(parts[3:]), name, lineno)
                if not NAME.match(name) or name in defs or name in words:
                    fail(lineno, "bad or repeated name %r" % name)
                if not re.match(r"^([0-9a-f]{2})+$", hexed):
                    fail(lineno, "bad bytes %r" % hexed)
                blobs.append((name, bytes.fromhex(hexed), source))
                words[name] = bytes.fromhex(hexed)
                continue
            if parts[0] == "words":
                if len(parts) < 4:
                    fail(lineno, "words row needs a name, rows and a source")
                name = parts[1]
                refs = []
                i = 2
                while i < len(parts) and ":" in parts[i]:
                    refs.append(parts[i])
                    i += 1
                source = check_source(" ".join(parts[i:]), name, lineno)
                if not NAME.match(name) or name in words or name in defs:
                    fail(lineno, "bad or repeated name %r" % name)
                data = b""
                for ref in refs:
                    table, row = ref.split(":", 1)
                    if (table, row) not in lookup:
                        fail(lineno, "words refers to %s, which no earlier row defines" % ref)
                    data += (lookup[(table, row)] & 0xFFFF).to_bytes(2, "little")
                blobs.append((name, data, source))
                words[name] = data
                magics.append(("words", name, len(data)))
                continue
            if parts[0] == "magics":
                if len(parts) != 2:
                    fail(lineno, "magics row needs one table")
                table = parts[1]
                if table not in by_table:
                    fail(lineno, "magics refers to table %s before it" % table)
                seen = []
                for name, value, _ in by_table[table]:
                    if value == 0 or value in seen:
                        continue
                    seen.append(value)
                    magics.append(("word", table, value))
                continue
            if len(parts) < 2:
                fail(lineno, "unrecognised line")
            table, name = parts[0], parts[1]
            if not tables or tables[-1][0] != table:
                fail(lineno, "row of %s outside its table" % table)
            if not NAME.match(name):
                fail(lineno, "bad name %r" % name)
            if len(parts) == 2:
                # a reference to a row an earlier table defines
                if name not in defs:
                    fail(lineno, "reference to %s, which no earlier table defines" % name)
                by_table[table].append((name, defs[name][0], None))
                continue
            if len(parts) < 5:
                fail(lineno, "row needs table, name, value, display and source")
            value_text, display = parts[2], parts[3]
            source = check_source(" ".join(parts[4:]), name, lineno)
            if name in defs:
                fail(lineno, "name %s is defined twice; a later table references it" % name)
            if name in words:
                fail(lineno, "name %s is already a byte string" % name)
            value = parse_value(value_text, lineno)
            if display == "=":
                display = name
            defs[name] = (value, display, source)
            lookup[(table, name)] = value
            by_table[table].append((name, value, display))
    for table, _ in tables:
        if not by_table[table]:
            sys.exit("gen-tables: table %s has no rows" % table)
    return tables, by_table, defs, blobs, magics, lookup, machines


HEADER = """# the PE/COFF constant tables, generated by tools/coff/gen-tables.py
# from tools/coff/tables.txt, which cites the PE Format specification and
# Wine's winnt.h and winuser.h at commit d38598c894f6.

use std.types.bool.bool;
use std.types.bool.false;
use std.types.bool.true;
use std.types.option.opt;
use std.types.size.usize;
use std.types.string.str;
use std.types.string.str_equals;

use mink.format.contract.Magic;

# one named constant: its name as the specification spells it, the spelling
# llvm-readobj prints for it, its value and the source that defines it. a signed value
# holds its 64-bit two's complement, so a field of narrower width compares against the
# value truncated to that width
pub rec Constant {
    name:    str;
    value:   u64;
    display: str;
    source:  str;
}

# one named byte string: its name, its bytes and the source that defines it
pub rec Blob {
    name:   str;
    data:   *u8;
    len:    usize;
    source: str;
}

# a table: the number of rows and where the first one lives
pub rec Set {
    count: usize;
    rows:  **Constant;
}
"""

LOOKUPS = """
pub fun name_of(s: *Set, value: u64) opt[*Constant] {
    var i: usize = 0;
    for (i < s.count) {
        if (s.rows[i].value == value) { ret opt[*Constant].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*Constant].none{};
}

pub fun by_name(s: *Set, name: str) opt[*Constant] {
    var i: usize = 0;
    for (i < s.count) {
        if (str_equals(s.rows[i].name, name)) { ret opt[*Constant].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*Constant].none{};
}

# one recorded constant of a source list
rec Expect {
    name:  str;
    value: u64;
}

# the table holds exactly the n recorded constants, each under its name with its
# value, each name once, and both lookups find every row
fun walk(s: *Set, want: *Expect, n: usize) bool {
    if (s.count != n) { ret false; }
    var i: usize = 0;
    for (i < n) {
        val got: opt[*Constant] = by_name(s, want[i].name);
        if (sel got.none)                    { ret false; }
        if (got.some.value != want[i].value) { ret false; }
        i = i + 1;
    }
    i = 0;
    for (i < n) {
        val row: *Constant = s.rows[i];
        var j:   usize     = 0;
        for (j < n) {
            if (j != i && str_equals(s.rows[j].name, row.name)) { ret false; }
            j = j + 1;
        }
        val named: opt[*Constant] = by_name(s, row.name);
        if (sel named.none)    { ret false; }
        if (named.some != row) { ret false; }
        val valued: opt[*Constant] = name_of(s, row.value);
        if (sel valued.none)                { ret false; }
        if (valued.some.value != row.value) { ret false; }
        i = i + 1;
    }
    ret true;
}

# the byte string holds the n bytes of the source list
fun blob_matches(b: *Blob, want: *u8, n: usize) bool {
    if (b.len != n) { ret false; }
    var i: usize = 0;
    for (i < n) {
        if (b.data[i] != want[i]) { ret false; }
        i = i + 1;
    }
    ret true;
}
"""


def bytes_literal(data):
    return ", ".join("0x%02x" % b for b in data)


MACHINE_PREFIX = "IMAGE_FILE_MACHINE_"

MACHINE_ROW_TYPE = '''
# the machine a row names: its code constant, the relocation set the machine uses (none
# when mink has no table for it) and the spelling llvm-readobj gives its import objects
# (none when unverified, so the dump prints the Machine line instead)
pub rec MachineRow {
    code:   *Constant;
    rel:    opt[*Set];
    format: opt[str];
}
'''

MACHINE_ROW_LOOKUP = '''
# the machine row of `code`, found by binary search over the rows sorted by code
pub fun machine(code: u64) opt[*MachineRow] {
    var lo: usize = 0;
    var hi: usize = MACHINES_BY_CODE_COUNT;
    for (lo < hi) {
        val mid: usize = lo + (hi - lo) / 2;
        val v: u64 = MACHINES_BY_CODE[mid].code.value::u64;
        if (v == code) { ret opt[*MachineRow].some{MACHINES_BY_CODE[mid]}; }
        if (v < code) { lo = mid + 1; }
        if (v > code) { hi = mid; }
    }
    ret opt[*MachineRow].none{};
}
'''


def emit(tables, by_table, defs, blobs, magics, lookup, machines):
    out = [HEADER]
    defined = set()
    for table, desc in tables:
        rows = by_table[table]
        out.append("# %s" % desc)
        for name, value, display in rows:
            if display is None:
                continue
            defined.add(name)
            out.append('pub val %s: Constant = Constant{name: "%s", value: 0x%x, display: "%s", source: "%s"};'
                       % (name, name, value, display, defs[name][2]))
        out.append("val %s_ROWS: [%d]*Constant = [%d]*Constant{" % (table, len(rows), len(rows)))
        for name, _, _ in rows:
            out.append("    ?%s," % name)
        out.append("};")
        out.append("pub val %s: Set = Set{count: %d, rows: ?%s_ROWS[0]};" % (table, len(rows), table))
        out.append("")
    machines = sorted(machines, key=lambda m: m[1])
    for a, b in zip(machines, machines[1:]):
        if not a[1] < b[1]:
            sys.exit("gen-tables: machine rows %s and %s are not in strictly increasing code order" % (a[0], b[0]))
    out.append(MACHINE_ROW_TYPE.strip("\n"))
    out.append("")
    for code, _, rel, fmt, _ in machines:
        if not code.startswith(MACHINE_PREFIX):
            sys.exit("gen-tables: machine %s lacks the %s prefix" % (code, MACHINE_PREFIX))
        rel_text = "opt[*Set].some{?%s}" % rel if rel else "opt[*Set].none{}"
        fmt_text = 'opt[str].some{"%s"}' % fmt if fmt else "opt[str].none{}"
        out.append("pub val MACHINE_ROW_%s: MachineRow = MachineRow{code: ?%s, rel: %s, format: %s};"
                   % (code[len(MACHINE_PREFIX):], code, rel_text, fmt_text))
    out.append("")
    out.append("val MACHINES_BY_CODE_COUNT: usize = %d;" % len(machines))
    out.append("val MACHINES_BY_CODE: [%d]*MachineRow = [%d]*MachineRow{" % (len(machines), len(machines)))
    for code, _, _, _, _ in machines:
        out.append("    ?MACHINE_ROW_%s," % code[len(MACHINE_PREFIX):])
    out.append("};")
    out.append(MACHINE_ROW_LOOKUP.strip("\n"))
    out.append("")
    for name, data, source in blobs:
        out.append("# %s" % source)
        out.append("pub val %s_BYTES: [%d]u8 = [%d]u8{%s};" % (name, len(data), len(data), bytes_literal(data)))
        out.append('pub val %s: Blob = Blob{name: "%s", data: ?%s_BYTES[0], len: %d, source: "%s"};'
                   % (name, name, name, len(data), source))
        out.append("")
    # the magic each word row yields: a machine word of the table's rows, or a signature
    entries = []
    for kind, name, size_or_value in magics:
        if kind == "words":
            entries.append((name, size_or_value, "?%s_BYTES[0]" % name))
    word_tables = [m for m in magics if m[0] == "word"]
    if word_tables:
        table_names = sorted(set(m[1] for m in word_tables))
        for table in table_names:
            values = [m[2] for m in word_tables if m[1] == table]
            data = []
            for v in values:
                data += [v & 0xFF, (v >> 8) & 0xFF]
            out.append("# the machine words of the %s table" % table)
            out.append("pub val %s_WORD_BYTES: [%d]u8 = [%d]u8{%s};"
                       % (table, len(data), len(data), bytes_literal(data)))
            out.append("")
            for i in range(len(values)):
                entries.append(("%s word %d" % (table, i), 2, "?%s_WORD_BYTES[%d]" % (table, 2 * i)))
    out.append("# every magic a file of this format starts with")
    out.append("pub val MAGIC_COUNT: usize = %d;" % len(entries))
    out.append("pub val MAGICS: [%d]Magic = [%d]Magic{" % (len(entries), len(entries)))
    for label, length, ptr in entries:
        out.append("    Magic{offset: 0, bytes: %s, len: %d}," % (ptr, length))
    out.append("};")
    out.append("")
    out.append(LOOKUPS.lstrip("\n"))
    for table, _ in tables:
        rows = by_table[table]
        out.append("val %s_WANT: [%d]Expect = [%d]Expect{" % (table, len(rows), len(rows)))
        for name, value, _ in rows:
            out.append('    Expect{name: "%s", value: 0x%x},' % (name, value))
        out.append("};")
        out.append("")
    for name, data, _ in blobs:
        out.append("val %s_WANT: [%d]u8 = [%d]u8{%s};" % (name, len(data), len(data), bytes_literal(data)))
        out.append("")
    out.append("test tables__rows_match_source {")
    for name, data, _ in blobs:
        out.append("    if (!blob_matches(?%s, ?%s_WANT[0], %d))  { ret 1; }" % (name, name, len(data)))
    for table, _ in tables:
        out.append("    if (!walk(?%s, ?%s_WANT[0], %d))  { ret 1; }" % (table, table, len(by_table[table])))
    out.append("    ret 0;")
    out.append("}")
    return "\n".join(out) + "\n"


def main():
    tables, by_table, defs, blobs, magics, lookup, machines = parse()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(emit(tables, by_table, defs, blobs, magics, lookup, machines))
    print("wrote %s: %d tables, %d rows, %d byte strings" % (
        OUT, len(tables), sum(len(r) for r in by_table.values()), len(blobs)))


if __name__ == "__main__":
    main()

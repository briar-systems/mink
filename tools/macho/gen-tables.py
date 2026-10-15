#!/usr/bin/env python3
# generate src/format/macho/model/tables.mach from tools/macho/constants.txt.
#
# run by hand from anywhere: python3 tools/macho/gen-tables.py
# the build never runs this. the output is deterministic, and the one walk
# test checks every table against the same recorded rows. a value several rows
# of a table share has exactly one canonical name, which lookup by value finds.

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(HERE, "constants.txt")
OUT = os.path.join(ROOT, "src", "format", "macho", "model", "tables.mach")

HEX = re.compile(r"^0x[0-9a-f]+$")
TEXT = re.compile(r'^"[^"\\]*"$')
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def parse(path):
    tables = []      # {kind, name, header, doc, rows: [(name, text)]}
    excludes = []    # (name, reason)
    marks = {}       # canonical name -> reason
    binds = []       # (cpu type name, subtype table name)
    doc = ""
    cur = None
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip():
            doc, cur = "", None
            continue
        if line.startswith("#"):
            doc = line[1:].strip()
            continue
        head = line.split()
        if head[0] in ("table", "text"):
            if len(head) != 3:
                raise SystemExit("%s:%d: %s NAME HEADER expected" % (path, n, head[0]))
            cur = {"kind": head[0], "name": head[1], "header": head[2], "doc": doc, "rows": []}
            tables.append(cur)
            doc = ""
        elif head[0] == "exclude":
            excludes.append((head[1], " ".join(head[2:])))
            cur = None
        elif head[0] == "subtypes":
            if len(head) != 3:
                raise SystemExit("%s:%d: subtypes CPU_TYPE TABLE expected" % (path, n))
            binds.append((head[1], head[2]))
            cur = None
        elif head[0] == "canonical":
            if len(head) < 3:
                raise SystemExit("%s:%d: canonical NAME REASON expected" % (path, n))
            if head[1] in marks:
                raise SystemExit("%s:%d: %s is marked canonical twice" % (path, n, head[1]))
            marks[head[1]] = " ".join(head[2:])
            cur = None
        else:
            if cur is None:
                raise SystemExit("%s:%d: row outside a table" % (path, n))
            if len(head) != 2:
                raise SystemExit("%s:%d: NAME VALUE expected" % (path, n))
            name, value = head
            if cur["kind"] == "table" and not HEX.match(value):
                raise SystemExit("%s:%d: hex value expected, got %s" % (path, n, value))
            if cur["kind"] == "text" and not TEXT.match(line.split(" ", 1)[1]):
                raise SystemExit("%s:%d: quoted text expected" % (path, n))
            if not IDENT.match(name):
                raise SystemExit("%s:%d: bad name %s" % (path, n, name))
            cur["rows"].append((name, line.split(" ", 1)[1]))
    return tables, excludes, marks, binds


def check(tables, excludes, marks, binds):
    names, sets = {}, {}
    for t in tables:
        if t["name"] in sets:
            raise SystemExit("table %s is named twice" % t["name"])
        sets[t["name"]] = t
        if not t["rows"]:
            raise SystemExit("table %s has no rows" % t["name"])
        for name, _ in t["rows"]:
            if name in names:
                raise SystemExit("constant %s is in two tables" % name)
            names[name] = t["name"]
    for name, _ in excludes:
        if name in names:
            raise SystemExit("constant %s is both a row and excluded" % name)
    for name in names:
        if name in sets:
            raise SystemExit("constant %s shares a name with a table" % name)
    for name in marks:
        if name not in names or sets[names[name]]["kind"] != "table":
            raise SystemExit("canonical mark names no numeric row: %s" % name)
    for t in tables:
        if t["kind"] == "table":
            t["keys"] = keys(t, marks)
    seen = set()
    for cpu, table in binds:
        if cpu not in t_by(tables, "CPU_TYPE")["keys"]:
            raise SystemExit("subtypes names %s, which is no canonical row of CPU_TYPE" % cpu)
        if table not in sets or sets[table]["kind"] != "table":
            raise SystemExit("subtypes names %s, which is no table" % table)
        if cpu in seen:
            raise SystemExit("cpu type %s is bound twice" % cpu)
        seen.add(cpu)


def t_by(tables, name):
    return next(t for t in tables if t["name"] == name)


def emit_binds(tables, binds):
    """one row per bound cpu type, ascending by its value, so lookup by value
    is a binary search."""
    values = dict(t_by(tables, "CPU_TYPE")["rows"])
    rows = sorted(binds, key=lambda b: int(values[b[0]], 16))
    n = len(rows)
    out = ["# the subtype table each cpu type reads its subtypes from, ascending by cpu type",
           "val CPU_TYPE_SUBTYPES: [%d]Subtypes = [%d]Subtypes{" % (n, n)]
    out += ["    Subtypes{cpu: ?%s, subtypes: ?%s}," % b for b in rows]
    out.append("};")
    out.append("")
    out.append(BINDING.rstrip("\n").replace("@N", str(n)))
    return out


def keys(t, marks):
    """the canonical name of each value of a table, ascending by value, refusing
    a shared value with no canonical name or with two, and a stale mark."""
    by_value = {}
    for name, val in t["rows"]:
        by_value.setdefault(int(val, 16), []).append(name)
    out = []
    for value in sorted(by_value):
        names = by_value[value]
        if len(names) == 1:
            if names[0] in marks:
                raise SystemExit("%s is marked canonical, but no other row of %s shares its value" % (names[0], t["name"]))
            out.append(names[0])
            continue
        chosen = [n for n in names if n in marks]
        if not chosen:
            raise SystemExit("value 0x%x of %s has no canonical name among %s" % (value, t["name"], " ".join(names)))
        if len(chosen) > 1:
            raise SystemExit("value 0x%x of %s has two canonical names: %s" % (value, t["name"], " ".join(chosen)))
        out.append(chosen[0])
    return out


def block(lines):
    """align a run of `pub val`/`val` declarations the way mach fmt does."""
    name_w = max(len(name) + 1 for _, name, _, _ in lines)
    type_w = max(len(ty) for _, _, ty, _ in lines)
    out = []
    for prefix, name, ty, body in lines:
        out.append("%s%s %s = %s" % (prefix.ljust(8), (name + ":").ljust(name_w), ty.ljust(type_w), body))
    return out


def emit_table(t):
    kind = t["kind"]
    rec = "Constant" if kind == "table" else "TextConstant"
    set_ty = "Set" if kind == "table" else "TextSet"
    rows = t["rows"]
    n = len(rows)
    out = ["# %s" % t["doc"]]
    decls = []
    for name, val in rows:
        if kind == "table":
            body = '%s{name: "%s", value: %s, source: "%s"};' % (rec, name, val, t["header"])
        else:
            body = '%s{name: "%s", text: %s, source: "%s"};' % (rec, name, val, t["header"])
        decls.append(("pub val", name, rec, body))
    rows_name = t["name"] + "_ROWS"
    refs = ["    ?%s," % name for name, _ in rows]
    decls.append(("val", rows_name, "[%d]*%s" % (n, rec), "[%d]*%s{" % (n, rec)))
    out += block(decls)
    out += refs
    out.append("};")
    if kind == "table":
        ks = t["keys"]
        keys_name = t["name"] + "_KEYS"
        out.append("val %s: [%d]*%s = [%d]*%s{" % (keys_name, len(ks), rec, len(ks), rec))
        out += ["    ?%s," % name for name in ks]
        out.append("};")
        out.append("pub val %s: %s = %s{count: %d, rows: ?%s[0], keyed: %d, keys: ?%s[0]};"
                   % (t["name"], set_ty, set_ty, n, rows_name, len(ks), keys_name))
    else:
        out.append("pub val %s: %s = %s{count: %d, rows: ?%s[0]};" % (t["name"], set_ty, set_ty, n, rows_name))
    return out


def emit_want(t):
    kind = t["kind"]
    n = len(t["rows"])
    out = []
    if kind == "table":
        out.append("val %s_WANT: [%d]Expect = [%d]Expect{" % (t["name"], n, n))
        for name, val in t["rows"]:
            canon = "true" if name in t["keys"] else "false"
            out.append('    Expect{name: "%s", value: %s, canonical: %s},' % (name, val, canon))
    else:
        out.append("val %s_WANT: [%d]ExpectText = [%d]ExpectText{" % (t["name"], n, n))
        for name, val in t["rows"]:
            out.append('    ExpectText{name: "%s", text: %s},' % (name, val))
    out.append("};")
    return out


HEADER = """# the Mach-O constant tables, generated by tools/macho/gen-tables.py from
# tools/macho/constants.txt. every value is the one the stated SDK header
# declares, at the revision src/format/macho.mach names for that header. one
# table per enumeration, so a value is named in its own enumeration.

use std.types.bool.bool;
use std.types.bool.false;
use std.types.bool.true;
use std.types.option.opt;
use std.types.size.usize;
use std.types.string.str;
use std.types.string.str_equals;

# one named constant: its name as the header spells it, its value and the
# header it comes from
pub rec Constant {
    name:   str;
    value:  u64;
    source: str;
}

# a table: the number of rows and where the first one lives, and the
# canonical row of each value, ascending by value
pub rec Set {
    count: usize;
    rows:  **Constant;
    keyed: usize;
    keys:  **Constant;
}

# one named string constant: its name, its text and the header it comes from
pub rec TextConstant {
    name:   str;
    text:   str;
    source: str;
}

# a table of string constants
pub rec TextSet {
    count: usize;
    rows:  **TextConstant;
}

# a cpu type and the table its subtypes are named in
rec Subtypes {
    cpu:      *Constant;
    subtypes: *Set;
}
"""

LOOKUPS = """# the canonical constant a table holds under a value
pub fun name_of(s: *Set, value: u64) opt[*Constant] {
    var lo: usize = 0;
    var hi: usize = s.keyed;
    for (lo < hi) {
        val mid: usize = lo + (hi - lo) / 2;
        val at:  u64   = s.keys[mid].value;
        if (at == value) { ret opt[*Constant].some{s.keys[mid]}; }
        if (at < value)  { lo = mid + 1; }
        or               { hi = mid; }
    }
    ret opt[*Constant].none{};
}

# the constant a table holds under a name
pub fun by_name(s: *Set, name: str) opt[*Constant] {
    var i: usize = 0;
    for (i < s.count) {
        if (str_equals(s.rows[i].name, name)) { ret opt[*Constant].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*Constant].none{};
}

# the string constant a table holds under a name
pub fun text_by_name(s: *TextSet, name: str) opt[*TextConstant] {
    var i: usize = 0;
    for (i < s.count) {
        if (str_equals(s.rows[i].name, name)) { ret opt[*TextConstant].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*TextConstant].none{};
}
"""

BINDING = """# the table of subtypes a cpu type names them in, or none when the header has
# no subtypes for it
pub fun subtypes_of(cputype: u64) opt[*Set] {
    var lo: usize = 0;
    var hi: usize = @N;
    for (lo < hi) {
        val mid: usize = lo + (hi - lo) / 2;
        val at:  u64   = CPU_TYPE_SUBTYPES[mid].cpu.value;
        if (at == cputype) { ret opt[*Set].some{CPU_TYPE_SUBTYPES[mid].subtypes}; }
        if (at < cputype)  { lo = mid + 1; }
        or                 { hi = mid; }
    }
    ret opt[*Set].none{};
}"""

TESTS = """
# one recorded constant of a source list, canonical when lookup by its value
# names it
rec Expect {
    name:      str;
    value:     u64;
    canonical: bool;
}

# one recorded string constant of a source list
rec ExpectText {
    name: str;
    text: str;
}

# the table holds exactly the n recorded constants, each under its name with its
# value, each name once, lookup by name finds every row, and lookup by value
# finds the canonical row of every value and nothing else
fun walk(s: *Set, want: *Expect, n: usize) bool {
    if (s.count != n) { ret false; }
    var keyed: usize = 0;
    var i:     usize = 0;
    for (i < n) {
        val got: opt[*Constant] = by_name(s, want[i].name);
        if (sel got.none)                    { ret false; }
        if (got.some.value != want[i].value) { ret false; }
        val valued: opt[*Constant] = name_of(s, want[i].value);
        if (sel valued.none)                                { ret false; }
        if ((valued.some == got.some) != want[i].canonical) { ret false; }
        if (want[i].canonical)                              { keyed = keyed + 1; }
        i = i + 1;
    }
    if (keyed != s.keyed) { ret false; }
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
        i = i + 1;
    }
    ret true;
}

# the string table holds exactly the n recorded string constants, each under its
# name with its text, each name once
fun walk_text(s: *TextSet, want: *ExpectText, n: usize) bool {
    if (s.count != n) { ret false; }
    var i: usize = 0;
    for (i < n) {
        val got: opt[*TextConstant] = text_by_name(s, want[i].name);
        if (sel got.none)                             { ret false; }
        if (!str_equals(got.some.text, want[i].text)) { ret false; }
        i = i + 1;
    }
    i = 0;
    for (i < n) {
        var j: usize = 0;
        for (j < n) {
            if (j != i && str_equals(s.rows[j].name, s.rows[i].name)) { ret false; }
            j = j + 1;
        }
        val named: opt[*TextConstant] = text_by_name(s, s.rows[i].name);
        if (sel named.none)          { ret false; }
        if (named.some != s.rows[i]) { ret false; }
        i = i + 1;
    }
    ret true;
}

# the cpu type's value finds the subtype table bound to it
fun bound(c: *Constant, s: *Set) bool {
    val got: opt[*Set] = subtypes_of(c.value);
    if (sel got.none) { ret false; }
    ret got.some == s;
}

"""


def emit_test(tables, binds):
    lines = []
    for t in tables:
        fn = "walk" if t["kind"] == "table" else "walk_text"
        want = "%s_WANT[0]" % t["name"]
        call = "if (!%s(?%s, ?%s, %d))" % (fn, t["name"], want, len(t["rows"]))
        lines.append((call, t["name"]))
    for cpu, table in binds:
        lines.append(("if (!bound(?%s, ?%s))" % (cpu, table), cpu))
    width = max(len(c) for c, _ in lines)
    return ["    %s { ret 1; }" % c.ljust(width) for c, _ in lines] + ["    ret 0;", "}"]


def main():
    tables, excludes, marks, binds = parse(DATA)
    check(tables, excludes, marks, binds)
    chunks = [HEADER.rstrip("\n"), LOOKUPS.rstrip("\n")]
    for t in tables:
        chunks.append("\n".join(emit_table(t)))
    chunks.append("\n".join(emit_binds(tables, binds)))
    chunks.append("\n".join(sum((emit_want(t) + [""] for t in tables), [])).rstrip("\n"))
    chunks.append(TESTS.strip("\n"))
    chunks.append("test tables__rows_match_source {\n" + "\n".join(emit_test(tables, binds)))
    text = "\n\n".join(chunks) + "\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s: %d tables, %d constants" % (OUT, len(tables), sum(len(t["rows"]) for t in tables)))


if __name__ == "__main__":
    main()

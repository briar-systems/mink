#!/usr/bin/env python3
# generate src/format/wasm/tables.mach from the vendored LLVM Wasm.h and WasmRelocs.def.
#
# run by hand from anywhere: python3 vendor/llvm/gen-wasm-tables.py
# the build never runs this. the output is deterministic, and every header name
# of a covered family is either classified below or excluded with a reason, so a
# constant cannot be left out by accident. the relocation rows carry whether the
# relocation record has an addend, a fact of the linking convention the header
# does not state, so the list below is checked against the header name by name.

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
WASM_H = os.path.join(HERE, "Wasm.h")
RELOCS_DEF = os.path.join(HERE, "WasmRelocs.def")
OUT = os.path.join(ROOT, "src", "format", "wasm", "tables.mach")
MACH = os.environ.get("MACH", "mach")

CORE = "WebAssembly core specification"
LINKING = "WebAssembly tool conventions, Linking"
DYNAMIC = "WebAssembly tool conventions, DynamicLinking"
PRODUCERS = "WebAssembly tool conventions, ProducersSection"

# every table, in output order: name, description, header prefix, source
TABLES = [
    ("SEC", "section ids", "WASM_SEC_", CORE),
    ("TYPE", "type codes", "WASM_TYPE_", CORE),
    ("EXTERNAL", "kinds of import and export", "WASM_EXTERNAL_", CORE),
    ("OPCODE", "opcodes of a constant expression", "WASM_OPCODE_", CORE),
    ("LIMITS", "limits flags", "WASM_LIMITS_FLAG_", CORE),
    ("DATA_SEGMENT", "data segment flags", "WASM_DATA_SEGMENT_", CORE),
    ("ELEM_SEGMENT", "element segment flags", "WASM_ELEM_SEGMENT_", CORE),
    ("TAG_ATTRIBUTE", "tag attributes", "WASM_TAG_ATTRIBUTE_", CORE),
    ("NAMES", "subsection ids of the name section", "WASM_NAMES_", CORE),
    ("FEATURE_PREFIX", "feature prefixes of the target_features section", "WASM_FEATURE_PREFIX_", LINKING),
    ("LINKING", "subsection ids of the linking section", "WASM_", LINKING),
    ("DYLINK", "subsection ids of the dylink.0 section", "WASM_DYLINK_", DYNAMIC),
    ("COMDAT", "kinds of a COMDAT member", "WASM_COMDAT_", LINKING),
    ("SYMBOL_TYPE", "kinds of a symbol", "WASM_SYMBOL_TYPE_", LINKING),
    ("SEG_FLAG", "segment info flags", "WASM_SEG_FLAG_", LINKING),
    ("SYMBOL", "symbol flags", "WASM_SYMBOL_", LINKING),
]

# the names each table takes, where the prefix alone does not pick them
EXPLICIT = {
    "OPCODE": [
        "WASM_OPCODE_END", "WASM_OPCODE_GLOBAL_GET", "WASM_OPCODE_I32_CONST", "WASM_OPCODE_I64_CONST",
        "WASM_OPCODE_F32_CONST", "WASM_OPCODE_F64_CONST", "WASM_OPCODE_I32_ADD", "WASM_OPCODE_I32_SUB",
        "WASM_OPCODE_I32_MUL", "WASM_OPCODE_I64_ADD", "WASM_OPCODE_I64_SUB", "WASM_OPCODE_I64_MUL",
        "WASM_OPCODE_REF_NULL", "WASM_OPCODE_REF_FUNC", "WASM_OPCODE_GC_PREFIX",
    ],
    "LINKING": ["WASM_SEGMENT_INFO", "WASM_INIT_FUNCS", "WASM_COMDAT_INFO", "WASM_SYMBOL_TABLE"],
    "SYMBOL": [
        "WASM_SYMBOL_BINDING_MASK", "WASM_SYMBOL_VISIBILITY_MASK", "WASM_SYMBOL_BINDING_GLOBAL",
        "WASM_SYMBOL_BINDING_WEAK", "WASM_SYMBOL_BINDING_LOCAL", "WASM_SYMBOL_VISIBILITY_DEFAULT",
        "WASM_SYMBOL_VISIBILITY_HIDDEN", "WASM_SYMBOL_UNDEFINED", "WASM_SYMBOL_EXPORTED",
        "WASM_SYMBOL_EXPLICIT_NAME", "WASM_SYMBOL_NO_STRIP", "WASM_SYMBOL_TLS", "WASM_SYMBOL_ABSOLUTE",
    ],
}

# header names outside every table, each with the reason
EXCLUDE = {
    "WASM_SEC_LAST_KNOWN": "an alias of the last section id",
    "WASM_MEM_ORDER_SEQ_CST": "an instruction immediate, which no section the reader decodes holds",
    "WASM_MEM_ORDER_ACQ_REL": "an instruction immediate, which no section the reader decodes holds",
    "WASM_MEM_ORDER_RMW_ACQ_REL": "an instruction immediate, which no section the reader decodes holds",
    "WASM_MEMARG_HAS_MEM_ORDER": "an instruction immediate, which no section the reader decodes holds",
    "WASM_ELEM_SEGMENT_MASK_HAS_ELEM_DESC": "a mask over the flags the table names",
    "WasmVersion": "written below as VERSION",
    "WasmMetadataVersion": "written below as METADATA_VERSION",
    "WasmDefaultPageSize": "written below as DEFAULT_PAGE_SIZE",
}

# opcodes of function bodies and of prefixed instruction spaces, which the reader
# holds as the bytes of a body and never decodes
EXCLUDE_OPCODES = {
    "WASM_OPCODE_CALL", "WASM_OPCODE_LOCAL_GET", "WASM_OPCODE_LOCAL_SET", "WASM_OPCODE_LOCAL_TEE",
    "WASM_OPCODE_GLOBAL_SET", "WASM_OPCODE_I32_STORE", "WASM_OPCODE_I64_STORE",
    "WASM_OPCODE_STRUCT_NEW", "WASM_OPCODE_STRUCT_NEW_DEFAULT", "WASM_OPCODE_ARRAY_NEW",
    "WASM_OPCODE_ARRAY_NEW_DEFAULT", "WASM_OPCODE_ARRAY_NEW_FIXED", "WASM_OPCODE_REF_I31",
    "WASM_OPCODE_BLOCK", "WASM_OPCODE_BR", "WASM_OPCODE_BR_TABLE", "WASM_OPCODE_RETURN",
    "WASM_OPCODE_DROP", "WASM_OPCODE_MISC_PREFIX", "WASM_OPCODE_MEMORY_INIT", "WASM_OPCODE_MEMORY_FILL",
    "WASM_OPCODE_DATA_DROP", "WASM_OPCODE_ATOMICS_PREFIX", "WASM_OPCODE_ATOMIC_NOTIFY",
    "WASM_OPCODE_I32_ATOMIC_WAIT", "WASM_OPCODE_I32_ATOMIC_STORE", "WASM_OPCODE_I32_RMW_CMPXCHG",
    "WASM_OPCODE_CATCH", "WASM_OPCODE_CATCH_REF", "WASM_OPCODE_CATCH_ALL", "WASM_OPCODE_CATCH_ALL_REF",
}

# the relocations whose record carries an addend, as Linking names them
ADDEND = {
    "R_WASM_MEMORY_ADDR_LEB", "R_WASM_MEMORY_ADDR_SLEB", "R_WASM_MEMORY_ADDR_I32",
    "R_WASM_FUNCTION_OFFSET_I32", "R_WASM_SECTION_OFFSET_I32", "R_WASM_MEMORY_ADDR_REL_SLEB",
    "R_WASM_MEMORY_ADDR_LEB64", "R_WASM_MEMORY_ADDR_SLEB64", "R_WASM_MEMORY_ADDR_I64",
    "R_WASM_MEMORY_ADDR_REL_SLEB64", "R_WASM_MEMORY_ADDR_TLS_SLEB", "R_WASM_FUNCTION_OFFSET_I64",
    "R_WASM_MEMORY_ADDR_LOCREL_I32", "R_WASM_MEMORY_ADDR_TLS_SLEB64", "R_WASM_MEMORY_ADDR_LOCREL_I64",
}

MASK64 = (1 << 64) - 1


def fail(msg):
    sys.exit("gen-wasm-tables: " + msg)


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def value_of(text, env):
    text = text.strip()
    m = re.match(r"^'(.)'$", text)
    if m:
        return ord(m.group(1))
    if re.match(r"^0[xX][0-9a-fA-F]+$", text) or re.match(r"^\d+$", text):
        return int(text, 0)
    if text in env:
        return None
    fail("cannot evaluate " + text)


# every WASM_* and Wasm* name the header defines, with its value, None for an alias
def parse_header(text):
    env = {}
    for m in re.finditer(r"\b(WASM_[A-Z0-9_]+)\s*=\s*([^,};\n]+)", text):
        name = m.group(1)
        if name in env:
            fail("constant defined twice: " + name)
        env[name] = value_of(m.group(2), env)
    for m in re.finditer(r"const\s+(?:unsigned|uint32_t|uint8_t)\s+(Wasm[A-Za-z]+)\s*=\s*([^;]+);", text):
        env[m.group(1)] = value_of(m.group(2), env)
    return env


def parse_relocs(text):
    rows = []
    for m in re.finditer(r"^WASM_RELOC\((\w+),\s*(\d+)\)", text, flags=re.M):
        rows.append((m.group(1), int(m.group(2))))
    if not rows:
        fail("no relocations in " + RELOCS_DEF)
    return rows


def mach_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt_hex(v):
    return "0x%x" % (v & MASK64)


def canonical(text):
    res = subprocess.run([MACH, "fmt", "-"], input=text, capture_output=True, text=True)
    if res.returncode != 0:
        fail("mach fmt failed: " + res.stdout + res.stderr)
    return res.stdout


def main():
    with open(WASM_H, encoding="utf-8") as f:
        env = parse_header(strip_comments(f.read()))
    with open(RELOCS_DEF, encoding="utf-8") as f:
        relocs = parse_relocs(f.read())

    # the explicitly listed tables take their names first, then each prefix
    # table takes every header name under its prefix that no table has yet
    rows = {}
    seen = {}
    ordered = [t for t in TABLES if t[0] in EXPLICIT] + [t for t in TABLES if t[0] not in EXPLICIT]
    for table, _desc, prefix, source in ordered:
        names = EXPLICIT.get(table)
        if names is None:
            names = [n for n in env if n.startswith(prefix) and n not in seen]
        for n in names:
            if n not in env:
                fail("header has no constant " + n)
            if n in EXCLUDE or n in EXCLUDE_OPCODES:
                continue
            if n in seen:
                fail("constant listed twice: " + n)
            if env[n] is None:
                fail("cannot evaluate " + n)
            seen[n] = table
            rows.setdefault(table, []).append((n, env[n], source))
    for table, _desc, _prefix, _source in TABLES:
        if table not in rows:
            fail("empty table " + table)
        rows[table].sort(key=lambda r: (r[1], r[0]))

    for n in env:
        if n in seen or n in EXCLUDE or n in EXCLUDE_OPCODES:
            continue
        fail("unclassified header constant " + n)
    for n in EXCLUDE:
        if n not in env:
            fail("excluded name not in the header: " + n)
    for n in EXCLUDE_OPCODES:
        if n not in env:
            fail("excluded opcode not in the header: " + n)
    for n in ADDEND:
        if n not in [r[0] for r in relocs]:
            fail("addend list names a relocation the header lacks: " + n)
    for n in ("WasmVersion", "WasmMetadataVersion", "WasmDefaultPageSize"):
        if env.get(n) is None:
            fail("cannot evaluate " + n)

    out = []
    out.append("# the wasm constant tables, generated by vendor/llvm/gen-wasm-tables.py")
    out.append("# from the LLVM Wasm.h and WasmRelocs.def pinned in vendor/llvm/REVISION.")
    out.append("")
    out.append("use std.types.bool.bool;")
    out.append("use std.types.bool.false;")
    out.append("use std.types.bool.true;")
    out.append("use std.types.option.opt;")
    out.append("use std.types.size.usize;")
    out.append("use std.types.string.str;")
    out.append("use std.types.string.str_equals;")
    out.append("")
    out.append("# one named constant: its name as the specification spells it, its value and")
    out.append("# the specification that defines it")
    out.append("pub rec Constant {")
    out.append("    name:   str;")
    out.append("    value:  u64;")
    out.append("    source: str;")
    out.append("}")
    out.append("")
    out.append("# a table: the number of rows and where the first one lives")
    out.append("pub rec Set {")
    out.append("    count: usize;")
    out.append("    rows:  **Constant;")
    out.append("}")
    out.append("")
    out.append("# a relocation type, and whether its record carries an addend")
    out.append("pub rec Relocation {")
    out.append("    name:   str;")
    out.append("    value:  u64;")
    out.append("    source: str;")
    out.append("    addend: bool;")
    out.append("}")
    out.append("")
    out.append("pub rec RelocationSet {")
    out.append("    count: usize;")
    out.append("    rows:  **Relocation;")
    out.append("}")
    out.append("")
    out.append("# the version of the binary format the reader decodes")
    out.append("pub val VERSION: u64 = %s;" % fmt_hex(env["WasmVersion"]))
    out.append("# the version of the linking section the reader decodes")
    out.append("pub val METADATA_VERSION: u64 = %s;" % fmt_hex(env["WasmMetadataVersion"]))
    out.append("# the bytes of a memory page, absent the custom page sizes proposal")
    out.append("pub val DEFAULT_PAGE_SIZE: u64 = %s;" % fmt_hex(env["WasmDefaultPageSize"]))
    out.append("")

    for table, desc, _prefix, _source in TABLES:
        rs = rows[table]
        out.append("# " + desc)
        for name, value, source in rs:
            out.append("pub val %s: Constant = Constant{name: %s, value: %s, source: %s};"
                       % (name, mach_str(name), fmt_hex(value), mach_str(source)))
        out.append("val %s_ROWS: [%d]*Constant = [%d]*Constant{" % (table, len(rs), len(rs)))
        for name, _value, _source in rs:
            out.append("    ?%s," % name)
        out.append("};")
        out.append("pub val %s: Set = Set{count: %d, rows: ?%s_ROWS[0]};" % (table, len(rs), table))
        out.append("")

    out.append("# relocation types, with whether the record carries an addend")
    for name, value in relocs:
        out.append("pub val %s: Relocation = Relocation{name: %s, value: %s, source: %s, addend: %s};"
                   % (name, mach_str(name), fmt_hex(value), mach_str(LINKING),
                      "true" if name in ADDEND else "false"))
    out.append("val RELOC_ROWS: [%d]*Relocation = [%d]*Relocation{" % (len(relocs), len(relocs)))
    for name, _value in relocs:
        out.append("    ?%s," % name)
    out.append("};")
    out.append("pub val RELOC: RelocationSet = RelocationSet{count: %d, rows: ?RELOC_ROWS[0]};" % len(relocs))
    out.append("")
    out.extend(LOOKUPS.split("\n"))
    for table, _desc, _prefix, _source in TABLES:
        out.extend(want_block(table, rows[table]))
    out.extend(want_block("RELOC", [(n, v, LINKING) for n, v in relocs]))
    out.extend(TEST_HEAD.split("\n"))
    for table, _desc, _prefix, _source in TABLES:
        out.append("    if (!walk(?%s, ?%s_WANT[0], %d)) { ret 1; }" % (table, table, len(rows[table])))
    out.append("    if (!walk_relocs(?RELOC, ?RELOC_WANT[0], %d)) { ret 1; }" % len(relocs))
    out.append("    ret 0;")
    out.append("}")
    out.append("")

    text = canonical("\n".join(out) + "\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s: %d tables, %d rows" % (
        OUT, len(TABLES) + 1, sum(len(v) for v in rows.values()) + len(relocs)))


LOOKUPS = """
# the constant a table holds under a value, the first one when values are shared
pub fun name_of(s: *Set, value: u64) opt[*Constant] {
    var i: usize = 0;
    for (i < s.count) {
        if (s.rows[i].value == value) { ret opt[*Constant].some{s.rows[i]}; }
        i = i + 1;
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

# the relocation type of a value, whose values ascend from zero
pub fun reloc_of(s: *RelocationSet, value: u64) opt[*Relocation] {
    if (value >= s.count::u64) { ret opt[*Relocation].none{}; }
    val row: *Relocation = s.rows[value::usize];
    if (row.value != value) { ret opt[*Relocation].none{}; }
    ret opt[*Relocation].some{row};
}

# the relocation type of a name
pub fun reloc_by_name(s: *RelocationSet, name: str) opt[*Relocation] {
    var i: usize = 0;
    for (i < s.count) {
        if (str_equals(s.rows[i].name, name)) { ret opt[*Relocation].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*Relocation].none{};
}
"""

TEST_HEAD = """
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
        if (sel got.none) { ret false; }
        if (got.some.value != want[i].value) { ret false; }
        i = i + 1;
    }
    i = 0;
    for (i < n) {
        val row: *Constant = s.rows[i];
        var j: usize = 0;
        for (j < n) {
            if (j != i && str_equals(s.rows[j].name, row.name)) { ret false; }
            j = j + 1;
        }
        val named: opt[*Constant] = by_name(s, row.name);
        if (sel named.none) { ret false; }
        if (named.some != row) { ret false; }
        val valued: opt[*Constant] = name_of(s, row.value);
        if (sel valued.none) { ret false; }
        if (valued.some.value != row.value) { ret false; }
        i = i + 1;
    }
    ret true;
}

# the relocations of walk, whose values are their positions
fun walk_relocs(s: *RelocationSet, want: *Expect, n: usize) bool {
    if (s.count != n) { ret false; }
    var i: usize = 0;
    for (i < n) {
        val got: opt[*Relocation] = reloc_by_name(s, want[i].name);
        if (sel got.none) { ret false; }
        if (got.some.value != want[i].value) { ret false; }
        val row: opt[*Relocation] = reloc_of(s, i::u64);
        if (sel row.none) { ret false; }
        if (row.some != s.rows[i] || row.some.value != i::u64) { ret false; }
        i = i + 1;
    }
    val past: opt[*Relocation] = reloc_of(s, n::u64);
    if (sel past.some) { ret false; }
    ret true;
}

test tables__rows_match_source {
"""


def want_block(table, rs):
    out = []
    out.append("val %s_WANT: [%d]Expect = [%d]Expect{" % (table, len(rs), len(rs)))
    for name, value, _src in rs:
        out.append("    Expect{name: %s, value: %s}," % (mach_str(name), fmt_hex(value)))
    out.append("};")
    out.append("")
    return out


if __name__ == "__main__":
    main()

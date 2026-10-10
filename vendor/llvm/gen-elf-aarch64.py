#!/usr/bin/env python3
# generate src/format/elf/reloc/aarch64.mach from the vendored LLVM AArch64.def.
#
# run by hand from anywhere: python3 vendor/llvm/gen-elf-aarch64.py, then mach fmt.
# the build never runs this. every LP64 name of the definition file must be
# classified below, so a relocation cannot be left without a row by accident.
# a row's kind is a shared kind of the neutral model, a kind every ELF pair
# shares, or a kind of the pair this module declares.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DEF = os.path.join(HERE, "AArch64.def")
OUT = os.path.join(ROOT, "src", "format", "elf", "reloc", "aarch64.mach")

# the kinds of the neutral model every pair shares
BASIC = {"NONE", "ABS64", "ABS32", "ABS16", "PC64", "PC32", "PC16"}
# the kinds every ELF pair shares, rows of src/format/elf/reloc/kinds.mach
SHARED = {"COPY", "GLOB_DAT", "JUMP_SLOT", "RELATIVE", "IRELATIVE", "TLSDESC", "TLSDESC_CALL",
          "DTPMOD64", "DTPOFF64", "TPOFF64", "PLT32", "GOTPCREL32"}

# the kind a code suffix maps to, where its name is not the suffix
KIND = {
    "NONE": "NONE", "ABS64": "ABS64", "ABS32": "ABS32", "ABS16": "ABS16",
    "PREL64": "PC64", "PREL32": "PC32", "PREL16": "PC16", "PLT32": "PLT32",
    "GOTPCREL32": "GOTPCREL32", "ADR_PREL_PG_HI21": "PAGE21",
    "ADD_ABS_LO12_NC": "LO12_ADD", "LDST8_ABS_LO12_NC": "LO12_LDST8",
    "LDST16_ABS_LO12_NC": "LO12_LDST16", "LDST32_ABS_LO12_NC": "LO12_LDST32",
    "LDST64_ABS_LO12_NC": "LO12_LDST64", "LDST128_ABS_LO12_NC": "LO12_LDST128",
    "TSTBR14": "BRANCH14", "CONDBR19": "BRANCH19", "JUMP26": "JUMP26", "CALL26": "CALL26",
    "ADR_GOT_PAGE": "GOT_PAGE21", "LD64_GOT_LO12_NC": "GOT_LO12",
    "TLS_DTPMOD64": "DTPMOD64", "TLS_DTPREL64": "DTPOFF64", "TLS_TPREL64": "TPOFF64",
}

# a field: container bytes, pieces (at, width), shift, insn, sign
MOVW_SIGN = (29, 2, 0, 2)
def lo12(scale):
    return (4, [(10, 12 - scale)], scale, True, None)

FIELDS = {
    "NONE": (0, [], 0, False, None),
    "DATA16": (2, [(0, 16)], 0, False, None),
    "DATA32": (4, [(0, 32)], 0, False, None),
    "DATA64": (8, [(0, 64)], 0, False, None),
    "BRANCH26": (4, [(0, 26)], 2, True, None),
    "BRANCH14": (4, [(5, 14)], 2, True, None),
    "LD19": (4, [(5, 19)], 2, True, None),
    "ADR21": (4, [(29, 2), (5, 19)], 0, True, None),
    "ADRP": (4, [(29, 2), (5, 19)], 12, True, None),
    "LO12_1": lo12(0), "LO12_2": lo12(1), "LO12_4": lo12(2), "LO12_8": lo12(3), "LO12_16": lo12(4),
    "LO15": (4, [(10, 12)], 3, True, None),
    "ADDHI12": (4, [(10, 12)], 12, True, None),
}
for g in range(4):
    FIELDS["MOVK%d" % g] = (4, [(5, 16)], 16 * g, True, None)
    FIELDS["MOVN%d" % g] = (4, [(5, 16)], 16 * g, True, MOVW_SIGN)

def sgn(bits, align=1): return ("signed", bits, align)
def uns(bits, align=1): return ("unsigned", bits, align)
def eit(bits, align=1): return ("either", bits, align)
def wrp(bits, align=1): return ("wrap", bits, align)

ROWS = []  # (suffix, kind caps, field, computation, range, relax suffix)
def row(suffix, caps, field, comp, rng, relax=None):
    ROWS.append((suffix, caps, field, comp, rng, relax))

# the checked move-wide groups take MOVN or MOVZ by sign, the unchecked take MOVK
ADRP_RANGE = sgn(33, 0x1000)
# classification of every LP64 name. caps is the neutral kind's capability set
row("NONE", "MARKER", "NONE", "NONE", wrp(1))
row("ABS64", "ABS", "DATA64", "ABS", wrp(64))
row("ABS32", "ABS", "DATA32", "ABS", eit(32))
row("ABS16", "ABS", "DATA16", "ABS", eit(16))
row("PREL64", "PC", "DATA64", "PC", wrp(64))
row("PREL32", "PC", "DATA32", "PC", eit(32))
row("PREL16", "PC", "DATA16", "PC", eit(16))
for i, g in enumerate(["G0", "G1", "G2"]):
    row("MOVW_UABS_" + g, "ABS", "MOVK%d" % i, "ABS", uns(16 * (i + 1)))
    row("MOVW_UABS_%s_NC" % g, "ABS", "MOVK%d" % i, "ABS", wrp(16))
row("MOVW_UABS_G3", "ABS", "MOVK3", "ABS", wrp(16))
for i, g in enumerate(["G0", "G1", "G2"]):
    row("MOVW_SABS_" + g, "ABS", "MOVN%d" % i, "ABS", sgn(16 * (i + 1) + 1))
row("LD_PREL_LO19", "PC", "LD19", "PC", sgn(21, 4))
row("ADR_PREL_LO21", "PC", "ADR21", "PC", sgn(21))
row("ADR_PREL_PG_HI21", "PC|PAGE", "ADRP", "PAGE", ADRP_RANGE)
row("ADR_PREL_PG_HI21_NC", "PC|PAGE", "ADRP", "PAGE", wrp(33, 0x1000))
row("ADD_ABS_LO12_NC", "ABS", "LO12_1", "ABS", wrp(12))
row("LDST8_ABS_LO12_NC", "ABS", "LO12_1", "ABS", wrp(12))
row("TSTBR14", "PC", "BRANCH14", "PC", sgn(16, 4))
row("CONDBR19", "PC", "LD19", "PC", sgn(21, 4))
row("JUMP26", "PC|PLT", "BRANCH26", "PLT", sgn(28, 4))
row("CALL26", "PC|PLT", "BRANCH26", "PLT", sgn(28, 4))
row("LDST16_ABS_LO12_NC", "ABS", "LO12_2", "ABS", wrp(12, 2))
row("LDST32_ABS_LO12_NC", "ABS", "LO12_4", "ABS", wrp(12, 4))
row("LDST64_ABS_LO12_NC", "ABS", "LO12_8", "ABS", wrp(12, 8))
row("LDST128_ABS_LO12_NC", "ABS", "LO12_16", "ABS", wrp(12, 16))
for i, g in enumerate(["G0", "G1", "G2"]):
    row("MOVW_PREL_" + g, "PC", "MOVN%d" % i, "PC", sgn(16 * (i + 1) + 1))
    row("MOVW_PREL_%s_NC" % g, "PC", "MOVK%d" % i, "PC", wrp(16))
row("MOVW_PREL_G3", "PC", "MOVK3", "PC", wrp(16))
for i, g in enumerate(["G0", "G1", "G2"]):
    row("MOVW_GOTOFF_" + g, "ABS|GOT", "MOVN%d" % i, "GOT_SLOT", sgn(16 * (i + 1) + 1))
    row("MOVW_GOTOFF_%s_NC" % g, "ABS|GOT", "MOVK%d" % i, "GOT_SLOT", wrp(16))
row("MOVW_GOTOFF_G3", "ABS|GOT", "MOVK3", "GOT_SLOT", wrp(16))
row("GOTREL64", "ABS|GOT", "DATA64", "GOT_OFF", wrp(64))
row("GOTREL32", "ABS|GOT", "DATA32", "GOT_OFF", sgn(32))
row("GOT_LD_PREL19", "PC|GOT", "LD19", "GOT_PC", sgn(21, 4))
row("LD64_GOTOFF_LO15", "ABS|GOT", "LO15", "GOT_SLOT", uns(15, 8))
row("ADR_GOT_PAGE", "PC|PAGE|GOT", "ADRP", "GOT_PAGE", ADRP_RANGE, "ADR_PREL_PG_HI21")
row("LD64_GOT_LO12_NC", "ABS|GOT", "LO12_8", "GOT", wrp(12, 8), "ADD_ABS_LO12_NC")
row("LD64_GOTPAGE_LO15", "ABS|GOT", "LO15", "GOT_PAGE_OFF", uns(15, 8))
row("PLT32", "PC|PLT", "DATA32", "PLT", sgn(32))
row("GOTPCREL32", "PC|GOT", "DATA32", "GOT_PC", sgn(32))
row("PATCHINST", "MARKER", "NONE", "NONE", wrp(1))
row("FUNCINIT64", "ABS", "DATA64", "ABS", wrp(64))

# general dynamic and local dynamic share the GOT-relative shapes
def tls_got(tag, relax):
    row(tag + "_ADR_PREL21", "PC|GOT|TLS", "ADR21", "GOT_PC", sgn(21))
    row(tag + "_ADR_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE, ("TLSLE_MOVW_TPREL_G1" if relax else None))
    row(tag + "_ADD_LO12_NC", "ABS|GOT|TLS", "LO12_1", "GOT", wrp(12), ("TLSLE_MOVW_TPREL_G0_NC" if relax else None))
    row(tag + "_MOVW_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33), ("TLSLE_MOVW_TPREL_G1" if relax else None))
    row(tag + "_MOVW_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16), ("TLSLE_MOVW_TPREL_G0_NC" if relax else None))
tls_got("TLSGD", True)
tls_got("TLSLD", False)
row("TLSLD_LD_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))

def tls_off(tag, mid, comp):
    # offset forms: MOVW groups, ADD high and low twelve, and the scaled loads
    row("%s_MOVW_%s_G2" % (tag, mid), "ABS|TLS", "MOVN2", comp, sgn(49))
    row("%s_MOVW_%s_G1" % (tag, mid), "ABS|TLS", "MOVN1", comp, sgn(33))
    row("%s_MOVW_%s_G1_NC" % (tag, mid), "ABS|TLS", "MOVK1", comp, wrp(16))
    row("%s_MOVW_%s_G0" % (tag, mid), "ABS|TLS", "MOVN0", comp, sgn(17))
    row("%s_MOVW_%s_G0_NC" % (tag, mid), "ABS|TLS", "MOVK0", comp, wrp(16))
    row("%s_ADD_%s_HI12" % (tag, mid), "ABS|TLS", "ADDHI12", comp, uns(24))
    row("%s_ADD_%s_LO12" % (tag, mid), "ABS|TLS", "LO12_1", comp, uns(12))
    row("%s_ADD_%s_LO12_NC" % (tag, mid), "ABS|TLS", "LO12_1", comp, wrp(12))
    for n, s in ((8, 0), (16, 1), (32, 2), (64, 3), (128, 4)):
        row("%s_LDST%d_%s_LO12" % (tag, n, mid), "ABS|TLS", "LO12_%d" % (1 << s), comp, uns(12, 1 << s))
        row("%s_LDST%d_%s_LO12_NC" % (tag, n, mid), "ABS|TLS", "LO12_%d" % (1 << s), comp, wrp(12, 1 << s))

tls_off("TLSLD", "DTPREL", "DTPOFF")
row("TLSIE_MOVW_GOTTPREL_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33), "TLSLE_MOVW_TPREL_G1")
row("TLSIE_MOVW_GOTTPREL_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16), "TLSLE_MOVW_TPREL_G0_NC")
row("TLSIE_ADR_GOTTPREL_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE, "TLSLE_MOVW_TPREL_G1")
row("TLSIE_LD64_GOTTPREL_LO12_NC", "ABS|GOT|TLS", "LO12_8", "GOT", wrp(12, 8), "TLSLE_MOVW_TPREL_G0_NC")
row("TLSIE_LD_GOTTPREL_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))
tls_off("TLSLE", "TPREL", "TPOFF")
row("TLSDESC_LD_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))
row("TLSDESC_ADR_PREL21", "PC|GOT|TLS", "ADR21", "GOT_PC", sgn(21))
row("TLSDESC_ADR_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE, "TLSLE_MOVW_TPREL_G1")
row("TLSDESC_LD64_LO12", "ABS|GOT|TLS", "LO12_8", "GOT", wrp(12, 8), "TLSLE_MOVW_TPREL_G0_NC")
row("TLSDESC_ADD_LO12", "ABS|GOT|TLS", "LO12_1", "GOT", wrp(12))
row("TLSDESC_OFF_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33), "TLSLE_MOVW_TPREL_G1")
row("TLSDESC_OFF_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16), "TLSLE_MOVW_TPREL_G0_NC")
row("TLSDESC_LDR", "MARKER", "NONE", "NONE", wrp(1))
row("TLSDESC_ADD", "MARKER", "NONE", "NONE", wrp(1))
row("TLSDESC_CALL", "MARKER", "NONE", "NONE", wrp(1))

# the dynamic loader applies these, so the linker writes no bytes for them
row("COPY", "MARKER|LOADER", "NONE", "NONE", wrp(1))
row("GLOB_DAT", "ABS|LOADER", "NONE", "SYMBOL", wrp(1))
row("JUMP_SLOT", "ABS|LOADER", "NONE", "SYMBOL", wrp(1))
row("RELATIVE", "IMAGE|LOADER", "NONE", "BASE", wrp(1))
row("TLSDESC", "ABS|TLS|LOADER", "NONE", "NONE", wrp(1))
row("IRELATIVE", "IMAGE|LOADER", "NONE", "BASE", wrp(1))
row("TLS_DTPMOD64", "ABS|TLS|LOADER", "NONE", "INDEX", wrp(1))
row("TLS_DTPREL64", "ABS|TLS|LOADER", "NONE", "DTPOFF", wrp(1))
row("TLS_TPREL64", "ABS|TLS|LOADER", "NONE", "TPOFF", wrp(1))

# pointer authentication: the static forms follow the plain forms they sign
row("AUTH_ABS64", "ABS", "NONE", "NONE", wrp(1))
for i, g in enumerate(["G0", "G0_NC", "G1", "G1_NC", "G2", "G2_NC", "G3"]):
    n = int(g[1])
    if g.endswith("_NC") or g == "G3":
        row("AUTH_MOVW_GOTOFF_" + g, "ABS|GOT", "MOVK%d" % n, "GOT_SLOT", wrp(16))
    else:
        row("AUTH_MOVW_GOTOFF_" + g, "ABS|GOT", "MOVN%d" % n, "GOT_SLOT", sgn(16 * (n + 1) + 1))
row("AUTH_GOT_LD_PREL19", "PC|GOT", "LD19", "GOT_PC", sgn(21, 4))
row("AUTH_LD64_GOTOFF_LO15", "ABS|GOT", "LO15", "GOT_SLOT", uns(15, 8))
row("AUTH_ADR_GOT_PAGE", "PC|PAGE|GOT", "ADRP", "GOT_PAGE", ADRP_RANGE)
row("AUTH_LD64_GOT_LO12_NC", "ABS|GOT", "LO12_8", "GOT", wrp(12, 8))
row("AUTH_LD64_GOTPAGE_LO15", "ABS|GOT", "LO15", "GOT_PAGE_OFF", uns(15, 8))
row("AUTH_GOT_ADD_LO12_NC", "ABS|GOT", "LO12_1", "GOT", wrp(12))
row("AUTH_GOT_ADR_PREL_LO21", "PC|GOT", "ADR21", "GOT_PC", sgn(21))
row("AUTH_TLSDESC_ADR_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE)
row("AUTH_TLSDESC_LD64_LO12", "ABS|GOT|TLS", "LO12_8", "GOT", wrp(12, 8))
row("AUTH_TLSDESC_ADD_LO12", "ABS|GOT|TLS", "LO12_1", "GOT", wrp(12))
row("AUTH_RELATIVE", "IMAGE|LOADER", "NONE", "BASE", wrp(1))
row("AUTH_GLOB_DAT", "ABS|LOADER", "NONE", "SYMBOL", wrp(1))
row("AUTH_TLSDESC", "ABS|TLS|LOADER", "NONE", "NONE", wrp(1))
row("AUTH_IRELATIVE", "IMAGE|LOADER", "NONE", "BASE", wrp(1))

TEST = """
#[embed("../../../../vendor/llvm/AArch64.def")]
val DEFINITION: [_]u8;

fun starts(at: usize, lead: str) bool {
    var i: usize = 0;
    for (lead[i] != 0) {
        if (at + i >= $length_of(DEFINITION) || DEFINITION[at + i] != lead[i]) { ret false; }
        i = i + 1;
    }
    ret true;
}

# the number after the comma at `at`, decimal or hexadecimal
fun number(at: usize) u32 {
    var r: usize = at + 1;
    var v: u32   = 0;
    for (DEFINITION[r] == ' ') { r = r + 1; }
    if (DEFINITION[r + 1] == 'x') {
        r = r + 2;
        for (DEFINITION[r] != ')') {
            val c: u8 = DEFINITION[r];
            if (c <= '9') { v = v * 16 + (c - '0')::u32; }
            or            { v = v * 16 + ((c | 0x20) - 'a' + 10)::u32; }
            r = r + 1;
        }
        ret v;
    }
    for (DEFINITION[r] != ')') {
        v = v * 10 + (DEFINITION[r] - '0')::u32;
        r = r + 1;
    }
    ret v;
}

test aarch64__every_source_relocation_has_its_row {
    var t:    testing.Testing;
    val made: err[A.Error] = testing.make(?t);
    if (sel made.err) { ret 1; }
    val built: res[row.Lookup, Fail] = row.build(testing.allocator_of(?t), ?SET);
    if (sel built.err) { ret 1; }
    var l:    row.Lookup = built.ok;
    var seen: usize      = 0;
    var at:   usize      = 0;
    for (at < $length_of(DEFINITION)) {
        val head: usize = at + 10;
        at = at + 1;
        if (!starts(head - 10, "ELF_RELOC(R_AARCH64_") || starts(head, "R_AARCH64_P32_")) { cnt; }
        var q: usize = head;
        for (DEFINITION[q] != ',') { q = q + 1; }
        val found: res[*Row, Fail] = row.by_key(?l, number(q));
        if (sel found.err) { ret 1; }
        val name: str   = found.ok.name;
        var k:    usize = 0;
        for (k < q - head) {
            if (name[k] != DEFINITION[head + k]) { ret 1; }
            k = k + 1;
        }
        if (name[k] != 0) { ret 1; }
        seen = seen + 1;
    }
    if (seen != ROW_COUNT) { ret 1; }
    val freed: err[Fail] = row.release_lookup(?l);
    if (sel freed.err) { ret 1; }
    testing.dnit(?t);
    ret 0;
}
"""

def read_def():
    out = []
    for line in open(DEF):
        m = re.match(r"ELF_RELOC\((R_AARCH64_\w+),\s*(0x[0-9a-fA-F]+|\d+)\)", line)
        if m and not m.group(1).startswith("R_AARCH64_P32_"):
            out.append((m.group(1)[len("R_AARCH64_"):], int(m.group(2), 0)))
    return out

def kind_name(suffix):
    return KIND.get(suffix, suffix)

def kind_ref(k):
    if k in BASIC:
        return "?reloc." + k
    if k in SHARED:
        return "?kinds." + k
    return "?" + k

# the thread-local access model a kind serves, from its name
def tls_of(k, caps):
    if "TLS" not in caps:
        return None
    if "TLSDESC" in k:
        return "desc"
    if "TLSGD" in k:
        return "gd"
    if "TLSLD" in k:
        return "ld"
    if "TLSIE" in k:
        return "ie"
    if "TLSLE" in k:
        return "le"
    sys.exit("no thread-local model for " + k)

# the slot role a kind reaches: its thread-local model's slots, a signed GOT
# slot, a GOT slot or a PLT entry
def slot_of(k, caps, tls):
    if "GOT" in caps:
        if tls:
            return {"gd": "TLS_GD", "ld": "TLS_LD", "ie": "TLS_IE", "desc": "TLSDESC"}[tls]
        if k.startswith("AUTH_"):
            return "AUTH_GOT"
        return "GOT"
    if "PLT" in caps:
        return "PLT"
    return None

def kind_decl(k, caps_text):
    caps = caps_text.split("|")
    tls = tls_of(k, caps)
    slot = slot_of(k, caps, tls)
    stated = [c for c in caps if c not in ("GOT", "PLT", "TLS")]
    if k.startswith("AUTH_"):
        stated.append("AUTH")
    takes = "NAMED"
    if "LOADER" in caps and "IMAGE" in caps:
        takes = "NAMELESS"
    elif "LOADER" in caps and "TLS" in caps:
        takes = "EITHER"
    parts = ["name: \"%s\"" % k.lower(), "caps: " + " | ".join("reloc." + c for c in stated), "takes: ?reloc.%s" % takes]
    if tls:
        parts.append("tls: Tls.%s{}" % tls)
    if slot:
        parts.append("slot: opt[*SlotRole].some{?slot.%s}" % slot)
    return "pub val %s: Kind = Kind{%s};" % (k, ", ".join(parts))

def main():
    src = read_def()
    by = {}
    for r in ROWS:
        if r[0] in by:
            sys.exit("classified twice: " + r[0])
        by[r[0]] = r
    names = [n for n, _ in src]
    for n in names:
        if n not in by:
            sys.exit("unclassified: " + n)
    for n in by:
        if n not in names:
            sys.exit("not in the definition file: " + n)
    for n, r in by.items():
        if r[5] is not None and r[5] not in by:
            sys.exit("relaxes to an unknown code: " + r[5])

    fields = []
    for n, _ in src:
        if by[n][2] not in fields:
            fields.append(by[n][2])
    kinds = []
    for n, _ in src:
        if kind_name(n) not in kinds:
            kinds.append(kind_name(n))
    relaxed = []
    for n, _ in src:
        t = by[n][5]
        if t and kind_name(t) not in relaxed:
            relaxed.append(kind_name(t))
    o = []
    w = o.append
    w("# the relocations of the Arm 64-bit ELF ABI, LP64")
    w("#")
    w("# one row for every relocation the vendored definition file lists, applied as")
    w("# RELA records. generated by vendor/llvm/gen-elf-aarch64.py. the instruction")
    w("# fields are bit ranges of a 32-bit little endian word, the checked move-wide")
    w("# forms hold their sign in the opcode, scaled low-12 forms check the alignment")
    w("# of the access, and the dynamic and marker codes hold no static field. a")
    w("# relaxation names the kind of the form it rewrites to.")
    w("")
    w("use std.types.bool.bool;")
    w("use std.types.bool.false;")
    w("use std.types.bool.true;")
    w("use std.types.error.err;")
    w("use std.types.option.opt;")
    w("use std.types.result.res;")
    w("use std.types.size.usize;")
    w("use std.types.string.str;")
    w("")
    w("use A: std.allocator;")
    w("use std.allocator.testing;")
    w("")
    w("use mink.base.fail.Fail;")
    w("use mink.catalog.arch.aarch64;")
    w("use mink.catalog.format;")
    w("use mink.catalog.slot;")
    w("use mink.catalog.slot.SlotRole;")
    w("use mink.format.elf.reloc.kinds;")
    w("use mink.model.reloc;")
    w("use mink.model.reloc.Kind;")
    w("use mink.model.reloc.Tls;")
    w("use mink.reloc.compute;")
    w("use mink.reloc.field;")
    w("use mink.reloc.field.Field;")
    w("use mink.reloc.field.Piece;")
    w("use mink.reloc.field.Range;")
    w("use mink.reloc.field.Sign;")
    w("use mink.reloc.row;")
    w("use mink.reloc.row.Addend;")
    w("use mink.reloc.row.Bytes;")
    w("use mink.reloc.row.Emit;")
    w("use mink.reloc.row.FieldChoice;")
    w("use mink.reloc.row.Rewrite;")
    w("use mink.reloc.row.Row;")
    w("use mink.reloc.row.Set;")
    w("")
    for f in fields:
        b, ps, sh, insn, sign = FIELDS[f]
        if not ps:
            continue
        w("val P_%s: [%d]Piece = [%d]Piece{%s};" % (f, len(ps), len(ps), ", ".join("Piece{at: %d, width: %d}" % p for p in ps)))
    w("")
    for f in fields:
        b, ps, sh, insn, sign = FIELDS[f]
        parts = ["bytes: %d" % b]
        if ps:
            parts += ["pieces: ?P_%s[0]" % f, "count: %d" % len(ps)]
        if sh:
            parts.append("shift: %d" % sh)
        if insn:
            parts.append("insn: true")
        if sign:
            parts.append("sign: opt[Sign].some{Sign{at: %d, width: %d, neg: %d, pos: %d}}" % sign)
        w("val F_%s: Field = Field{%s};" % (f, ", ".join(parts)))
    w("")
    for f in fields:
        w("val C_%s: [1]FieldChoice = [1]FieldChoice{FieldChoice{field: ?F_%s}};" % (f, f))
    w("")
    declared = set()
    for n, _ in src:
        k = kind_name(n)
        if k in BASIC or k in SHARED or k in declared:
            continue
        declared.add(k)
        w(kind_decl(k, by[n][1]))
    w("")
    for k in relaxed:
        w("val TO_%s_KINDS: [1]*Kind = [1]*Kind{%s};" % (k, kind_ref(k)))
        w("val TO_%s: Rewrite = Rewrite{name: \"to %s\", emit: Emit.bytes{Bytes{}}, kinds: ?TO_%s_KINDS[0], kind_count: 1, keeps_ct: true};" % (k, k.lower(), k))
        w("val TO_%s_ONLY: [1]*Rewrite = [1]*Rewrite{?TO_%s};" % (k, k))
    w("")
    w("val ROW_COUNT: usize = %d;" % len(src))
    w("val ROWS: [ROW_COUNT]Row = [ROW_COUNT]Row{")
    for n, code in src:
        _, caps, f, comp, rng, relax = by[n]
        chk, bits, align = rng
        parts = [
            "key: 0x%x" % code,
            "name: \"R_AARCH64_%s\"" % n,
            "kind: %s" % kind_ref(kind_name(n)),
            "fields: ?C_%s[0]" % f,
            "field_count: 1",
            "value: ?compute.%s" % comp,
            "range: Range{check: field.Check.%s{}, bits: %d, align: 0x%x}" % (chk, bits, align),
            "addend: Addend.record{}",
        ]
        if relax:
            parts.append("rewrites: ?TO_%s_ONLY[0]" % kind_name(relax))
            parts.append("rewrite_count: 1")
        w("    Row{")
        for x in parts:
            w("        %s," % x)
        w("    },")
    w("};")
    w("")
    w("val KIND_COUNT: usize = %d;" % len(kinds))
    w("val KINDS: [KIND_COUNT]*Kind = [KIND_COUNT]*Kind{%s};" % ", ".join(kind_ref(k) for k in kinds))
    w("")
    w("# the relocations of the ELF and AArch64 pair")
    w("pub val SET: Set = Set{format: ?format.ELF, arch: ?aarch64.AARCH64, rows: ?ROWS[0], count: ROW_COUNT, kinds: ?KINDS[0], kind_count: KIND_COUNT};")
    o.append(TEST)
    open(OUT, "w").write("\n".join(o) + "\n")

main()

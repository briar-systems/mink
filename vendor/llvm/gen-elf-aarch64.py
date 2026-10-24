#!/usr/bin/env python3
# generate src/format/elf/reloc/aarch64.mach and its kinds module
# src/format/elf/reloc/aarch64/kinds.mach from the vendored LLVM AArch64.def.
#
# run by hand from anywhere: python3 vendor/llvm/gen-elf-aarch64.py, then mach fmt.
# the build never runs this. every LP64 name of the definition file must be
# classified below, so a relocation cannot be left without a row by accident.
# a row's kind is a kind of the neutral model every pair or every AArch64 pair
# shares, a kind every ELF pair shares, or a kind of the pair its kinds module
# declares.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DEF = os.path.join(HERE, "AArch64.def")
OUT = os.path.join(ROOT, "src", "format", "elf", "reloc", "aarch64.mach")
KINDS_OUT = os.path.join(ROOT, "src", "format", "elf", "reloc", "aarch64", "kinds.mach")

# the kinds of the neutral model every pair shares
BASIC = {"NONE", "ABS64", "ABS32", "ABS16", "PC64", "PC32", "PC16", "BRANCH32",
         # the kinds the AArch64 pairs share, rows of the neutral model too
         "PAGE21", "LO12_ADD", "LO12_LDST8", "LO12_LDST16", "LO12_LDST32", "LO12_LDST64", "LO12_LDST128",
         "JUMP26", "CALL26", "BRANCH19", "BRANCH14", "LD_PREL_LO19", "ADR_PREL_LO21", "GOT_PAGE21", "GOT_LO12",
         "TLSDESC_LD_PREL19", "TLSDESC_ADR_PREL21", "TLSDESC_ADR_PAGE21", "TLSDESC_LD64_LO12", "TLSDESC_ADD_LO12",
         "TLSDESC_OFF_G1", "TLSDESC_OFF_G0_NC", "TLSDESC_LDR", "TLSDESC_ADD", "TLSIE_MOVW_GOTTPREL_G1",
         "TLSIE_MOVW_GOTTPREL_G0_NC", "TLSIE_ADR_GOTTPREL_PAGE21", "TLSIE_LD64_GOTTPREL_LO12_NC",
         "TLSIE_LD_GOTTPREL_PREL19"}
# the kinds every ELF pair shares, rows of src/format/elf/reloc/kinds.mach
SHARED = {"COPY", "GLOB_DAT", "JUMP_SLOT", "RELATIVE", "IRELATIVE", "TLSDESC", "TLSDESC_CALL",
          "DTPMOD64", "DTPOFF64", "TPOFF64", "PLT32", "GOTPCREL32"}

# the neutral kinds the pair has no form for, and why
REFUSAL_SOURCE = "ELF for the Arm 64-bit Architecture"
REFUSALS = [
    ("ABS8", "no relocation writes an absolute 8-bit field"),
    ("ABS32S", "no instruction sign-extends a 32-bit absolute, and R_AARCH64_ABS32 accepts either signedness"),
    ("PC8", "no relocation writes a place-relative 8-bit field"),
    ("DIFF8", "no relocation subtracts a second symbol"),
    ("DIFF16", "no relocation subtracts a second symbol"),
    ("DIFF32", "no relocation subtracts a second symbol"),
    ("DIFF64", "no relocation subtracts a second symbol"),
    ("TLV_PAGE21", "the Mach-O thread-local variable model has no ELF form"),
    ("TLV_LO12", "the Mach-O thread-local variable model has no ELF form"),
    ("SECREL_HI12", "no relocation counts from the target's section"),
    ("SECREL_LO12_ADD", "no relocation counts from the target's section"),
    ("SECREL_LO12_LDST8", "no relocation counts from the target's section"),
    ("SECREL_LO12_LDST16", "no relocation counts from the target's section"),
    ("SECREL_LO12_LDST32", "no relocation counts from the target's section"),
    ("SECREL_LO12_LDST64", "no relocation counts from the target's section"),
    ("SECREL_LO12_LDST128", "no relocation counts from the target's section"),
]

# the neutral kinds a code is written for besides the kind it reads as, each
# a row of that code's field, computation and range: (kind, code suffix)
WRITES = [
    ("BRANCH32", "CALL26"),
]

# the kinds of records a relaxation rewrites that no code reads as, each
# written under a code whose field it shares, with its own computation:
# (kind, caps, code suffix, computation). an ADRP a relaxation drops writes
# nothing and keeps the value it was weighed by, written as NONE
RELAXED = [
    ("ADRP_RELAXED", "PC", "NONE", "PC"),
]

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

# a row's forms are the name of its forms in the pair's forms module,
# src/format/elf/reloc/aarch64/forms.mach
ROWS = []  # (suffix, kind caps, field, computation, range, forms)
def row(suffix, caps, field, comp, rng, forms=None):
    ROWS.append((suffix, caps, field, comp, rng, forms))

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
row("ADR_PREL_PG_HI21", "PC|PAGE", "ADRP", "PAGE", ADRP_RANGE, forms="PAGE")
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
row("GOTREL64", "GOTREL", "DATA64", "GOT_OFF", wrp(64))
row("GOTREL32", "GOTREL", "DATA32", "GOT_OFF", sgn(32))
row("GOT_LD_PREL19", "PC|GOT", "LD19", "GOT_PC", sgn(21, 4))
row("LD64_GOTOFF_LO15", "ABS|GOT", "LO15", "GOT_SLOT", uns(15, 8))
row("ADR_GOT_PAGE", "PC|PAGE|GOT", "ADRP", "GOT_PAGE", ADRP_RANGE, forms="GOT_PAGE")
row("LD64_GOT_LO12_NC", "ABS|GOT", "LO12_8", "GOT", wrp(12, 8))
row("LD64_GOTPAGE_LO15", "ABS|GOT", "LO15", "GOT_PAGE_OFF", uns(15, 8))
row("PLT32", "PC|PLT", "DATA32", "PLT", sgn(32))
row("GOTPCREL32", "PC|GOT", "DATA32", "GOT_PC", sgn(32))
row("PATCHINST", "MARKER", "NONE", "NONE", wrp(1))
row("FUNCINIT64", "ABS", "DATA64", "ABS", wrp(64))

# general dynamic and local dynamic share the GOT-relative shapes. lld
# links neither, so neither takes a transition
def tls_got(tag):
    row(tag + "_ADR_PREL21", "PC|GOT|TLS", "ADR21", "GOT_PC", sgn(21))
    row(tag + "_ADR_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE)
    row(tag + "_ADD_LO12_NC", "ABS|GOT|TLS", "LO12_1", "GOT", wrp(12))
    row(tag + "_MOVW_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33))
    row(tag + "_MOVW_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16))
tls_got("TLSGD")
tls_got("TLSLD")
row("TLSLD_LD_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))

def tls_off(tag, mid, comp):
    # offset forms: MOVW groups, ADD high and low twelve, and the scaled loads
    row("%s_MOVW_%s_G2" % (tag, mid), "ABS|TLS", "MOVN2", comp, sgn(49))
    row("%s_MOVW_%s_G1" % (tag, mid), "ABS|TLS", "MOVN1", comp, sgn(33))
    row("%s_MOVW_%s_G1_NC" % (tag, mid), "ABS|TLS", "MOVK1", comp, wrp(16))
    row("%s_MOVW_%s_G0" % (tag, mid), "ABS|TLS", "MOVN0", comp, sgn(17))
    row("%s_MOVW_%s_G0_NC" % (tag, mid), "ABS|TLS", "MOVK0", comp, wrp(16))
    row("%s_ADD_%s_HI12" % (tag, mid), "ABS|TLS", "ADDHI12", comp, uns(24), forms=("TLSLE_HI12" if tag == "TLSLE" else None))
    row("%s_ADD_%s_LO12" % (tag, mid), "ABS|TLS", "LO12_1", comp, uns(12))
    row("%s_ADD_%s_LO12_NC" % (tag, mid), "ABS|TLS", "LO12_1", comp, wrp(12))
    for n, s in ((8, 0), (16, 1), (32, 2), (64, 3), (128, 4)):
        row("%s_LDST%d_%s_LO12" % (tag, n, mid), "ABS|TLS", "LO12_%d" % (1 << s), comp, uns(12, 1 << s))
        row("%s_LDST%d_%s_LO12_NC" % (tag, n, mid), "ABS|TLS", "LO12_%d" % (1 << s), comp, wrp(12, 1 << s))

tls_off("TLSLD", "DTPREL", "DTPOFF")
# the small code model's initial exec and descriptor sequences take the
# transitions lld writes, the move-wide sequences none
row("TLSIE_MOVW_GOTTPREL_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33))
row("TLSIE_MOVW_GOTTPREL_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16))
row("TLSIE_ADR_GOTTPREL_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE, forms="TLSIE_PAGE")
row("TLSIE_LD64_GOTTPREL_LO12_NC", "ABS|GOT|TLS", "LO12_8", "GOT", wrp(12, 8), forms="TLSIE_LO12")
row("TLSIE_LD_GOTTPREL_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))
tls_off("TLSLE", "TPREL", "TPOFF")
row("TLSDESC_LD_PREL19", "PC|GOT|TLS", "LD19", "GOT_PC", sgn(21, 4))
row("TLSDESC_ADR_PREL21", "PC|GOT|TLS", "ADR21", "GOT_PC", sgn(21))
row("TLSDESC_ADR_PAGE21", "PC|PAGE|GOT|TLS", "ADRP", "GOT_PAGE", ADRP_RANGE, forms="TLSDESC_PAGE")
row("TLSDESC_LD64_LO12", "ABS|GOT|TLS", "LO12_8", "GOT", wrp(12, 8), forms="TLSDESC_LD")
row("TLSDESC_ADD_LO12", "ABS|GOT|TLS", "LO12_1", "GOT", wrp(12), forms="TLSDESC_ADD")
row("TLSDESC_OFF_G1", "ABS|GOT|TLS", "MOVN1", "GOT_SLOT", sgn(33))
row("TLSDESC_OFF_G0_NC", "ABS|GOT|TLS", "MOVK0", "GOT_SLOT", wrp(16))
row("TLSDESC_LDR", "MARKER", "NONE", "NONE", wrp(1))
row("TLSDESC_ADD", "MARKER", "NONE", "NONE", wrp(1))
row("TLSDESC_CALL", "MARKER", "NONE", "NONE", wrp(1), forms="TLSDESC_CALL")

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
    val sets: [1]*row.Set             = [1]*row.Set{?SET};
    var g:    res[row.Registry, Fail] = row.make(testing.allocator_of(?t), ?sets[0], 1);
    if (sel g.err) { ret 1; }
    val l: res[*row.Lookup, Fail] = row.find(?g.ok, SET.format, SET.arch);
    if (sel l.err) { ret 1; }
    var seen: usize = 0;
    var at:   usize = 0;
    for (at < $length_of(DEFINITION)) {
        val head: usize = at + 10;
        at = at + 1;
        if (!starts(head - 10, "ELF_RELOC(R_AARCH64_") || starts(head, "R_AARCH64_P32_")) { cnt; }
        var q: usize = head;
        for (DEFINITION[q] != ',') { q = q + 1; }
        val found: res[*Row, Fail] = row.by_key(l.ok, number(q));
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
    val freed: err[Fail] = row.release(?g.ok);
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
    return "?aarch64_kinds." + k

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

    fields = []
    for n, _ in src:
        if by[n][2] not in fields:
            fields.append(by[n][2])
    kinds = []
    for n, _ in src:
        if kind_name(n) not in kinds:
            kinds.append(kind_name(n))
    for k, _ in WRITES:
        kinds.append(k)
    for k, _, _, _ in RELAXED:
        kinds.append(k)
    o = []
    w = o.append
    w("# the relocations of the Arm 64-bit ELF ABI, LP64")
    w("#")
    w("# one row for every relocation the vendored definition file lists, applied as")
    w("# RELA records. generated by vendor/llvm/gen-elf-aarch64.py. the instruction")
    w("# fields are bit ranges of a 32-bit little endian word, the checked move-wide")
    w("# forms hold their sign in the opcode, scaled low-12 forms check the alignment")
    w("# of the access, and the dynamic and marker codes hold no static field. the")
    w("# forms a row relaxes to are its forms module's, and the kinds only this pair")
    w("# states its kinds module's.")
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
    w("use mink.format.elf.reloc.kinds;")
    w("use aarch64_kinds: mink.format.elf.reloc.aarch64.kinds;")
    w("use mink.format.elf.reloc.aarch64.forms;")
    w("use mink.model.reloc;")
    w("use mink.model.reloc.Kind;")
    w("use mink.reloc.compute;")
    w("use mink.reloc.field;")
    w("use mink.reloc.field.Field;")
    w("use mink.reloc.field.Piece;")
    w("use mink.reloc.field.Range;")
    w("use mink.reloc.field.Sign;")
    w("use mink.reloc.leb;")
    w("use mink.reloc.row;")
    w("use mink.reloc.row.Addend;")
    w("use mink.reloc.row.FieldChoice;")
    w("use mink.reloc.row.Refusal;")
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
    d = []
    d.append("# the relocation kinds only the AArch64 ELF pair states")
    d.append("#")
    d.append("# the handles a producer names an AArch64 relocation by. generated by")
    d.append("# vendor/llvm/gen-elf-aarch64.py with the pair module, whose rows apply them.")
    d.append("")
    d.append("use std.types.option.opt;")
    d.append("")
    d.append("use mink.catalog.slot;")
    d.append("use mink.catalog.slot.SlotRole;")
    d.append("use mink.model.reloc;")
    d.append("use mink.model.reloc.Kind;")
    d.append("use mink.model.reloc.Tls;")
    d.append("")
    declared = set()
    for n, _ in src:
        k = kind_name(n)
        if k in BASIC or k in SHARED or k in declared:
            continue
        declared.add(k)
        d.append(kind_decl(k, by[n][1]))
    for k, caps, _, _ in RELAXED:
        d.append(kind_decl(k, caps))
    codes = dict((n, code) for n, code in src)
    def emit_row(n, kind, forms, computed=None):
        _, caps, f, comp, rng, _ = by[n]
        if computed:
            comp = computed
        chk, bits, align = rng
        parts = [
            "key: 0x%x" % codes[n],
            "name: \"R_AARCH64_%s\"" % n,
            "kind: %s" % kind_ref(kind),
            "fields: ?C_%s[0]" % f,
            "field_count: 1",
            "value: ?compute.%s" % comp,
            "range: Range{check: field.Check.%s{}, bits: %d, align: 0x%x}" % (chk, bits, align),
            "addend: Addend.record{}",
        ]
        if forms:
            parts.append("rewrites: ?forms.%s_FORMS[0]" % forms)
            parts.append("rewrite_count: forms.%s_COUNT" % forms)
        w("    Row{")
        for x in parts:
            w("        %s," % x)
        w("    },")
    w("val ROW_COUNT: usize = %d;" % len(src))
    w("val ROWS: [ROW_COUNT]Row = [ROW_COUNT]Row{")
    for n, code in src:
        emit_row(n, kind_name(n), by[n][5])
    w("};")
    w("")
    w("# the kinds a code is written for besides the kind it reads as")
    w("val WRITE_COUNT: usize = %d;" % (len(WRITES) + len(RELAXED)))
    w("val WRITES: [WRITE_COUNT]Row = [WRITE_COUNT]Row{")
    for k, n in WRITES:
        emit_row(n, k, None)
    for k, _, n, comp in RELAXED:
        emit_row(n, k, None, comp)
    w("};")
    w("")
    w("val KIND_COUNT: usize = %d;" % len(kinds))
    w("val KINDS: [KIND_COUNT]*Kind = [KIND_COUNT]*Kind{%s};" % ", ".join(kind_ref(k) for k in kinds))
    w("")
    w("val REFUSALS_COUNT: usize = %d;" % len(REFUSALS))
    w("val REFUSALS: [REFUSALS_COUNT]Refusal = [REFUSALS_COUNT]Refusal{")
    for k, why in REFUSALS:
        w("    Refusal{kind: ?reloc.%s, why: \"%s\", source: \"%s\"}," % (k, why, REFUSAL_SOURCE))
    w("};")
    w("")
    w("# the relocations of the ELF and AArch64 pair")
    w("pub val SET: Set = Set{format: ?format.ELF, arch: ?aarch64.AARCH64, rows: ?ROWS[0], count: ROW_COUNT, kinds: ?KINDS[0], kind_count: KIND_COUNT, refusals: ?REFUSALS[0], refusal_count: REFUSALS_COUNT, writes: ?WRITES[0], write_count: WRITE_COUNT, shared: ?leb.ROWS[0], shared_count: leb.COUNT};")
    o.append(TEST)
    open(OUT, "w").write("\n".join(o) + "\n")
    os.makedirs(os.path.dirname(KINDS_OUT), exist_ok=True)
    open(KINDS_OUT, "w").write("\n".join(d) + "\n")

main()

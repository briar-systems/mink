#!/usr/bin/env python3
# generate src/format/elf/model/tables.mach from the vendored LLVM headers.
#
# run by hand from anywhere: python3 vendor/llvm/gen-elf-tables.py
# the build never runs this. the output is deterministic, and every header
# name in a covered family is either classified below or excluded with a reason,
# so a constant cannot be left out by accident.

import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ELF_H = os.path.join(HERE, "ELF.h")
DT_DEF = os.path.join(HERE, "DynamicTags.def")
OUT = os.path.join(ROOT, "src", "format", "elf", "model", "tables.mach")

# every table, in output order: name, description
TABLES = [
    ("SHT", "section types of the generic ABI"),
    ("SHF", "section flags of the generic ABI"),
    ("PT", "segment types of the generic ABI"),
    ("PF", "segment flags of the generic ABI"),
    ("STT", "symbol types"),
    ("STB", "symbol bindings"),
    ("STV", "symbol visibilities"),
    ("NT_CORE", "note types of the core owner"),
    ("NT_GNU", "note types of the GNU owner"),
    ("GNU_PROPERTY", "GNU property types"),
    ("ELFOSABI", "OS and ABI identifiers"),
    ("EM", "machine identifiers"),
    ("ET", "file types"),
    ("DF_1", "DT_FLAGS_1 bits"),
    ("EI", "e_ident indices"),
    ("ELFCLASS", "file classes"),
    ("ELFDATA", "data encodings"),
    ("EV", "versions of the object file format"),
    ("SHN", "special section indices"),
    ("PN", "extended program header count"),
    ("ELFCOMPRESS", "compression types of compressed sections"),
    ("VER_DEF", "version definition versions and flags"),
    ("VER_NEED", "version dependency versions"),
    ("VER_FLG", "version definition flags"),
    ("VER_NDX", "version indices of symbols"),
    ("GRP", "section group flags"),
    ("STN", "symbol table index of the undefined symbol"),
    ("VERSYM", "version index bits of symbol versions"),
    ("SHT_X86_64", "section types of the x86-64 psABI"),
    ("SHT_AARCH64", "section types of the AArch64 ABI"),
    ("SHT_RISCV", "section types of the RISC-V psABI"),
    ("SHF_X86_64", "section flags of the x86-64 psABI"),
    ("SHF_AARCH64", "section flags of the AArch64 ABI"),
    ("PT_AARCH64", "segment types of the AArch64 ABI"),
    ("PT_RISCV", "segment types of the RISC-V psABI"),
    ("STO_AARCH64", "symbol other bits of the AArch64 ABI"),
    ("STO_RISCV", "symbol other bits of the RISC-V psABI"),
    ("EF_RISCV", "e_flags of the RISC-V psABI"),
    ("NT_X86_64", "note types of the x86-64 core owner"),
    ("NT_AARCH64", "note types of the AArch64 core owner"),
    ("GNU_PROPERTY_X86_64", "GNU property types of the x86-64 psABI"),
    ("GNU_PROPERTY_X86_64_FEATURE_1", "x86-64 feature bits of GNU_PROPERTY_X86_FEATURE_1_AND"),
    ("GNU_PROPERTY_X86_64_FEATURE_2", "x86-64 feature bits of GNU_PROPERTY_X86_FEATURE_2_USED"),
    ("GNU_PROPERTY_X86_64_ISA_1", "x86-64 ISA level bits of GNU_PROPERTY_X86_ISA_1_USED"),
    ("GNU_PROPERTY_AARCH64", "GNU property types of the AArch64 ABI"),
    ("GNU_PROPERTY_AARCH64_FEATURE_1", "AArch64 feature bits of GNU_PROPERTY_AARCH64_FEATURE_1_AND"),
    ("GNU_PROPERTY_RISCV", "GNU property types of the RISC-V psABI"),
    ("GNU_PROPERTY_RISCV_FEATURE_1", "RISC-V feature bits of GNU_PROPERTY_RISCV_FEATURE_1_AND"),
    ("AARCH64_PAUTH_PLATFORM", "PAuth platform identifiers"),
]

DT_TABLES = [
    ("DT", "dynamic tags of the generic ABI and its extensions"),
    ("DT_AARCH64", "dynamic tags of the AArch64 ABI"),
    ("DT_RISCV", "dynamic tags of the RISC-V psABI"),
]

# the families whose header names must all be classified
FAMILIES = (
    "SHT_", "SHF_", "PT_", "PF_", "STT_", "STB_", "STV_", "STO_", "NT_",
    "GNU_PROPERTY_", "ELFOSABI_", "EM_", "EF_RISCV_", "AARCH64_PAUTH_PLATFORM_",
    "ET_", "EI_", "ELFCLASS", "ELFDATA", "EV_", "SHN_", "PN_", "ELFCOMPRESS_",
    "VER_", "GRP_", "STN_", "VERSYM_",
)

# name lists per table: "table source NAME NAME ..." one per line
INCLUDE = """
SHT gABI SHT_NULL SHT_PROGBITS SHT_SYMTAB SHT_STRTAB SHT_RELA SHT_HASH SHT_DYNAMIC SHT_NOTE SHT_NOBITS SHT_REL SHT_SHLIB SHT_DYNSYM SHT_INIT_ARRAY SHT_FINI_ARRAY SHT_PREINIT_ARRAY SHT_GROUP SHT_SYMTAB_SHNDX SHT_LOOS SHT_HIOS SHT_LOPROC SHT_HIPROC SHT_LOUSER SHT_HIUSER
SHT RELR_proposal SHT_RELR
SHT Android SHT_ANDROID_REL SHT_ANDROID_RELA SHT_ANDROID_RELR
SHT GNU SHT_GNU_ATTRIBUTES SHT_GNU_HASH SHT_GNU_verdef SHT_GNU_verneed SHT_GNU_versym SHT_GNU_SFRAME
SHT LLVM SHT_LLVM_ADDRSIG SHT_LLVM_DEPENDENT_LIBRARIES
SHF gABI SHF_WRITE SHF_ALLOC SHF_EXECINSTR SHF_MERGE SHF_STRINGS SHF_INFO_LINK SHF_LINK_ORDER SHF_OS_NONCONFORMING SHF_GROUP SHF_TLS SHF_COMPRESSED SHF_EXCLUDE SHF_MASKOS SHF_MASKPROC
SHF GNU SHF_GNU_RETAIN
SHF Solaris SHF_SUNW_NODISCARD
PT gABI PT_NULL PT_LOAD PT_DYNAMIC PT_INTERP PT_NOTE PT_SHLIB PT_PHDR PT_TLS PT_LOOS PT_HIOS PT_LOPROC PT_HIPROC
PT GNU PT_GNU_EH_FRAME PT_GNU_STACK PT_GNU_RELRO PT_GNU_PROPERTY PT_GNU_SFRAME
PT Solaris PT_SUNW_EH_FRAME PT_SUNW_UNWIND
PT OpenBSD PT_OPENBSD_MUTABLE PT_OPENBSD_RANDOMIZE PT_OPENBSD_WXNEEDED PT_OPENBSD_NOBTCFI PT_OPENBSD_SYSCALLS PT_OPENBSD_BOOTDATA
PF gABI PF_X PF_W PF_R PF_MASKOS PF_MASKPROC
STT gABI STT_NOTYPE STT_OBJECT STT_FUNC STT_SECTION STT_FILE STT_COMMON STT_TLS STT_LOOS STT_HIOS STT_LOPROC STT_HIPROC
STT GNU STT_GNU_IFUNC
STB gABI STB_LOCAL STB_GLOBAL STB_WEAK STB_LOOS STB_HIOS STB_LOPROC STB_HIPROC
STB GNU STB_GNU_UNIQUE
STV gABI STV_DEFAULT STV_INTERNAL STV_HIDDEN STV_PROTECTED
NT_CORE core NT_PRSTATUS NT_FPREGSET NT_PRPSINFO NT_TASKSTRUCT NT_AUXV NT_PSTATUS NT_FPREGS NT_PSINFO NT_LWPSTATUS NT_LWPSINFO NT_WIN32PSTATUS NT_FILE NT_PRXFPREG NT_SIGINFO
NT_GNU GNU NT_GNU_ABI_TAG NT_GNU_HWCAP NT_GNU_BUILD_ID NT_GNU_GOLD_VERSION NT_GNU_PROPERTY_TYPE_0
GNU_PROPERTY GNU GNU_PROPERTY_STACK_SIZE GNU_PROPERTY_NO_COPY_ON_PROTECTED
ELFOSABI gABI ELFOSABI_NONE ELFOSABI_HPUX ELFOSABI_NETBSD ELFOSABI_GNU ELFOSABI_HURD ELFOSABI_SOLARIS ELFOSABI_AIX ELFOSABI_IRIX ELFOSABI_FREEBSD ELFOSABI_TRU64 ELFOSABI_MODESTO ELFOSABI_OPENBSD ELFOSABI_OPENVMS ELFOSABI_NSK ELFOSABI_AROS ELFOSABI_FENIXOS ELFOSABI_CLOUDABI ELFOSABI_STANDALONE
EM gABI EM_*
ET gABI ET_NONE ET_REL ET_EXEC ET_DYN ET_CORE ET_LOOS ET_HIOS ET_LOPROC ET_HIPROC
DF_1 GNU DF_1_PIE
EI gABI EI_MAG0 EI_MAG1 EI_MAG2 EI_MAG3 EI_CLASS EI_DATA EI_VERSION EI_OSABI EI_ABIVERSION EI_PAD EI_NIDENT
ELFCLASS gABI ELFCLASSNONE ELFCLASS32 ELFCLASS64
ELFDATA gABI ELFDATANONE ELFDATA2LSB ELFDATA2MSB
EV gABI EV_NONE EV_CURRENT
SHN gABI SHN_UNDEF SHN_LORESERVE SHN_LOPROC SHN_HIPROC SHN_LOOS SHN_HIOS SHN_ABS SHN_COMMON SHN_XINDEX SHN_HIRESERVE
PN gABI PN_XNUM
ELFCOMPRESS gABI ELFCOMPRESS_ZLIB ELFCOMPRESS_ZSTD ELFCOMPRESS_LOOS ELFCOMPRESS_HIOS ELFCOMPRESS_LOPROC ELFCOMPRESS_HIPROC
VER_DEF GNU VER_DEF_NONE VER_DEF_CURRENT
VER_NEED GNU VER_NEED_NONE VER_NEED_CURRENT
VER_FLG GNU VER_FLG_BASE VER_FLG_WEAK VER_FLG_INFO
VER_NDX GNU VER_NDX_LOCAL VER_NDX_GLOBAL
GRP gABI GRP_COMDAT GRP_MASKOS GRP_MASKPROC
STN gABI STN_UNDEF
VERSYM GNU VERSYM_VERSION VERSYM_HIDDEN
SHT_X86_64 x86-64_psABI SHT_X86_64_UNWIND
SHT_AARCH64 aaelf64 SHT_AARCH64_ATTRIBUTES SHT_AARCH64_AUTH_RELR SHT_AARCH64_MEMTAG_GLOBALS_STATIC SHT_AARCH64_MEMTAG_GLOBALS_DYNAMIC
SHT_RISCV RISC-V_psABI SHT_RISCV_ATTRIBUTES
SHF_X86_64 x86-64_psABI SHF_X86_64_LARGE
SHF_AARCH64 aaelf64 SHF_AARCH64_PURECODE
PT_AARCH64 aaelf64 PT_AARCH64_MEMTAG_MTE
PT_RISCV RISC-V_psABI PT_RISCV_ATTRIBUTES
STO_AARCH64 aaelf64 STO_AARCH64_VARIANT_PCS
STO_RISCV RISC-V_psABI STO_RISCV_VARIANT_CC
EF_RISCV RISC-V_psABI EF_RISCV_RVC EF_RISCV_FLOAT_ABI EF_RISCV_FLOAT_ABI_SOFT EF_RISCV_FLOAT_ABI_SINGLE EF_RISCV_FLOAT_ABI_DOUBLE EF_RISCV_FLOAT_ABI_QUAD EF_RISCV_RVE EF_RISCV_TSO
NT_X86_64 core NT_X86_XSTATE
NT_AARCH64 core NT_ARM_VFP NT_ARM_TLS NT_ARM_HW_BREAK NT_ARM_HW_WATCH NT_ARM_SVE NT_ARM_PAC_MASK NT_ARM_TAGGED_ADDR_CTRL NT_ARM_SSVE NT_ARM_ZA NT_ARM_ZT NT_ARM_FPMR NT_ARM_POE NT_ARM_GCS
GNU_PROPERTY_X86_64 x86-64_psABI GNU_PROPERTY_X86_FEATURE_1_AND GNU_PROPERTY_X86_FEATURE_2_NEEDED GNU_PROPERTY_X86_ISA_1_NEEDED GNU_PROPERTY_X86_FEATURE_2_USED GNU_PROPERTY_X86_ISA_1_USED
GNU_PROPERTY_X86_64_FEATURE_1 x86-64_psABI GNU_PROPERTY_X86_FEATURE_1_IBT GNU_PROPERTY_X86_FEATURE_1_SHSTK
GNU_PROPERTY_X86_64_FEATURE_2 x86-64_psABI GNU_PROPERTY_X86_FEATURE_2_X86 GNU_PROPERTY_X86_FEATURE_2_X87 GNU_PROPERTY_X86_FEATURE_2_MMX GNU_PROPERTY_X86_FEATURE_2_XMM GNU_PROPERTY_X86_FEATURE_2_YMM GNU_PROPERTY_X86_FEATURE_2_ZMM GNU_PROPERTY_X86_FEATURE_2_FXSR GNU_PROPERTY_X86_FEATURE_2_XSAVE GNU_PROPERTY_X86_FEATURE_2_XSAVEOPT GNU_PROPERTY_X86_FEATURE_2_XSAVEC
GNU_PROPERTY_X86_64_ISA_1 x86-64_psABI GNU_PROPERTY_X86_ISA_1_BASELINE GNU_PROPERTY_X86_ISA_1_V2 GNU_PROPERTY_X86_ISA_1_V3 GNU_PROPERTY_X86_ISA_1_V4
GNU_PROPERTY_AARCH64 aaelf64 GNU_PROPERTY_AARCH64_FEATURE_1_AND
GNU_PROPERTY_AARCH64 pauthabielf64 GNU_PROPERTY_AARCH64_FEATURE_PAUTH
GNU_PROPERTY_AARCH64_FEATURE_1 aaelf64 GNU_PROPERTY_AARCH64_FEATURE_1_BTI GNU_PROPERTY_AARCH64_FEATURE_1_PAC GNU_PROPERTY_AARCH64_FEATURE_1_GCS
GNU_PROPERTY_RISCV RISC-V_psABI GNU_PROPERTY_RISCV_FEATURE_1_AND
GNU_PROPERTY_RISCV_FEATURE_1 RISC-V_psABI GNU_PROPERTY_RISCV_FEATURE_1_CFI_LP_UNLABELED GNU_PROPERTY_RISCV_FEATURE_1_CFI_SS GNU_PROPERTY_RISCV_FEATURE_1_CFI_LP_FUNC_SIG
AARCH64_PAUTH_PLATFORM pauthabielf64 AARCH64_PAUTH_PLATFORM_INVALID AARCH64_PAUTH_PLATFORM_BAREMETAL
"""

# names a family may hold that are not rows, each with the reason
EXCLUDE = {
    "SHT_CREL": "llvm experimental, its value is not fixed",
    "SHT_HEX_ORDERED": "hexagon section type",
    "SHF_ARM_PURECODE": "arm section flag",
    "SHF_HEX_GPREL": "hexagon section flag",
    "ELFOSABI_LINUX": "alias of ELFOSABI_GNU",
    "ELFOSABI_ARM_FDPIC": "arm OS ABI",
    "ELFOSABI_CUDA": "nvidia OS ABI",
    "ELFOSABI_CUDA_V2": "nvidia OS ABI",
    "ELFOSABI_AMDGPU_HSA": "amdgpu OS ABI",
    "ELFOSABI_AMDGPU_PAL": "amdgpu OS ABI",
    "ELFOSABI_AMDGPU_MESA3D": "amdgpu OS ABI",
    "ELFOSABI_ARM": "arm OS ABI",
    "ELFOSABI_C6000_ELFABI": "TMS320C6000 OS ABI",
    "ELFOSABI_C6000_LINUX": "TMS320C6000 OS ABI",
    "ELFOSABI_FIRST_ARCH": "range bound of architecture-specific values",
    "ELFOSABI_LAST_ARCH": "range bound of architecture-specific values",
    "EM_ECOG1X": "alias of EM_ECOG1",
    "GNU_PROPERTY_X86_UINT32_OR_LO": "base of property numbers, not a type",
    "GNU_PROPERTY_X86_UINT32_OR_AND_LO": "base of property numbers, not a type",
    "STO_PPC64_LOCAL_BIT": "powerpc64 field",
    "STO_PPC64_LOCAL_MASK": "powerpc64 field",
}

# families whose names are excluded wholesale, with the reason
EXCLUDE_PREFIX = [
    ("SHT_LLVM_", "llvm internal section types"),
    ("SHT_ARM_", "arm section types"),
    ("SHT_MSP430_", "msp430 section types"),
    ("SHT_CSKY_", "csky section types"),
    ("SHT_HEXAGON_", "hexagon section types"),
    ("SHT_MIPS_", "mips section types"),
    ("SHN_HEXAGON_", "hexagon section indices"),
    ("SHN_MIPS_", "mips section indices"),
    ("SHN_AMDGPU_", "amdgpu section indices"),
    ("SHF_MIPS_", "mips section flags"),
    ("SHF_XCORE_", "xcore section flags"),
    ("STT_AMDGPU_", "amdgpu symbol type"),
    ("STO_MIPS_", "mips symbol other bits"),
    ("STO_PPC64_", "powerpc64 symbol other bits"),
    ("PT_ARM_", "arm segment types"),
    ("PT_MIPS_", "mips segment types"),
    ("NT_PPC_", "powerpc note types"),
    ("NT_386_", "i386 note types"),
    ("NT_S390_", "s390 note types"),
    ("NT_FREEBSD_", "freebsd note owner"),
    ("NT_NETBSDCORE_", "netbsd note owner"),
    ("NT_OPENBSD_", "openbsd note owner"),
    ("NT_AMD_", "amd note owner"),
    ("NT_AMDGPU_", "amdgpu note owner"),
    ("NT_LLVM_", "llvm note owner"),
    ("NT_ANDROID_", "android note owner"),
    ("NT_MEMTAG_", "android memtag note owner"),
    ("NT_GNU_BUILD_ATTRIBUTE_", "gnu build attribute owner"),
    ("NT_VERSION", "owner-less note type of another owner"),
    ("NT_ARCH", "owner-less note type of another owner"),
    ("GNU_PROPERTY_X86_UINT32_", "base of property numbers, not a type"),
    ("AARCH64_PAUTH_PLATFORM_LLVM_", "llvm pauth platform"),
    ("EF_RISCV_NONSTANDARD", "vendor relocation helper"),
]

# dynamic tags: name, source, whether d_un is an address (d_ptr)
# the rule for values in DT_ENCODING to DT_LOOS is the gABI's: even is d_ptr,
# odd is d_val. the rows here are that rule applied and the tags below
# DT_ENCODING and in the extensions named by the source.
DT_INCLUDE = """
DT NULL gABI no
DT NEEDED gABI no
DT PLTRELSZ gABI no
DT PLTGOT gABI yes
DT HASH gABI yes
DT STRTAB gABI yes
DT SYMTAB gABI yes
DT RELA gABI yes
DT RELASZ gABI no
DT RELAENT gABI no
DT STRSZ gABI no
DT SYMENT gABI no
DT INIT gABI yes
DT FINI gABI yes
DT SONAME gABI no
DT RPATH gABI no
DT SYMBOLIC gABI no
DT REL gABI yes
DT RELSZ gABI no
DT RELENT gABI no
DT PLTREL gABI no
DT DEBUG gABI yes
DT TEXTREL gABI no
DT JMPREL gABI yes
DT BIND_NOW gABI no
DT INIT_ARRAY gABI yes
DT FINI_ARRAY gABI yes
DT INIT_ARRAYSZ gABI no
DT FINI_ARRAYSZ gABI no
DT RUNPATH gABI no
DT FLAGS gABI no
DT PREINIT_ARRAY gABI yes
DT PREINIT_ARRAYSZ gABI no
DT SYMTAB_SHNDX gABI yes
DT RELRSZ RELR_proposal no
DT RELR RELR_proposal yes
DT RELRENT RELR_proposal no
DT LOOS gABI no
DT HIOS gABI no
DT LOPROC gABI no
DT HIPROC gABI no
DT ANDROID_REL Android yes
DT ANDROID_RELSZ Android no
DT ANDROID_RELA Android yes
DT ANDROID_RELASZ Android no
DT ANDROID_RELR Android yes
DT ANDROID_RELRSZ Android no
DT ANDROID_RELRENT Android no
DT GNU_HASH GNU yes
DT TLSDESC_PLT GNU yes
DT TLSDESC_GOT GNU yes
DT RELACOUNT GNU no
DT RELCOUNT GNU no
DT FLAGS_1 GNU no
DT VERSYM GNU yes
DT VERDEF GNU yes
DT VERDEFNUM GNU no
DT VERNEED GNU yes
DT VERNEEDNUM GNU no
DT AUXILIARY gABI no
DT USED gABI no
DT FILTER gABI no
DT_AARCH64 AARCH64_BTI_PLT aaelf64 no
DT_AARCH64 AARCH64_PAC_PLT aaelf64 no
DT_AARCH64 AARCH64_VARIANT_PCS aaelf64 no
DT_AARCH64 AARCH64_MEMTAG_MODE aaelf64 no
DT_AARCH64 AARCH64_MEMTAG_HEAP aaelf64 no
DT_AARCH64 AARCH64_MEMTAG_STACK aaelf64 no
DT_AARCH64 AARCH64_MEMTAG_GLOBALS aaelf64 yes
DT_AARCH64 AARCH64_MEMTAG_GLOBALSSZ aaelf64 no
DT_AARCH64 AARCH64_AUTH_RELRSZ pauthabielf64 no
DT_AARCH64 AARCH64_AUTH_RELR pauthabielf64 yes
DT_AARCH64 AARCH64_AUTH_RELRENT pauthabielf64 no
DT_RISCV RISCV_VARIANT_CC RISC-V_psABI no
"""

DT_EXCLUDE = {
    "CREL": "llvm experimental, its value is not fixed",
    "ENCODING": "boundary of the d_un rule, not a tag",
}

DT_EXCLUDE_MACRO = {
    "MIPS_": "mips dynamic tags",
    "PPC_": "powerpc dynamic tags",
    "PPC64_": "powerpc64 dynamic tags",
    "HEXAGON_": "hexagon dynamic tags",
    "SPARC_": "sparc dynamic tags",
}


def fail(msg):
    sys.exit("gen-elf-tables: " + msg)


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def eval_expr(expr, env):
    expr = re.sub(r"\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b", r"\1", expr.replace("\n", " "))
    node = ast.parse(expr.strip(), mode="eval").body
    return _eval_node(node, env)


BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitAnd: lambda a, b: a & b,
    ast.LShift: lambda a, b: a << b,
    ast.RShift: lambda a, b: a >> b,
}


def _eval_node(node, env):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env or env[node.id] is None:
            raise ValueError("unknown name " + node.id)
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        return BIN_OPS[type(node.op)](_eval_node(node.left, env), _eval_node(node.right, env))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, env)
    raise ValueError("unsupported expression")


def split_top(body):
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def parse_enums(text):
    # every enumerator in file order, name -> value (None when it cannot be evaluated)
    env = {}
    for m in re.finditer(r"\benum\b[^{;]*\{", text):
        depth, i = 1, m.end()
        while depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = "\n".join(l for l in text[m.end():i - 1].split("\n") if not l.lstrip().startswith("#"))
        nxt = 0
        for entry in split_top(body):
            entry = entry.strip()
            if not entry:
                continue
            em = re.match(r"^(\w+)\s*(?:=\s*(.+))?$", entry, flags=re.S)
            if not em:
                continue
            name, expr = em.group(1), em.group(2)
            if expr is None:
                value = nxt
            else:
                try:
                    value = eval_expr(expr, env)
                except (ValueError, SyntaxError):
                    value = None
            if name in env and env[name] != value:
                fail("conflicting values for " + name)
            env[name] = value
            nxt = (value + 1) if value is not None else None
    return env


def parse_dt(text):
    # (macro, name, value) in file order
    rows = []
    for line in text.split("\n"):
        m = re.match(r"^\s*(AARCH64_|RISCV_|MIPS_|PPC_|PPC64_|HEXAGON_|SPARC_)?DYNAMIC_TAG(?:_MARKER)?\(\s*(\w+)\s*,\s*(0[xX][0-9a-fA-F]+|\d+)\s*\)", line)
        if m:
            rows.append((m.group(1) or "", m.group(2), int(m.group(3), 0)))
    return rows


def parse_inc(text):
    # table name -> list of (name, source, extra) from the INCLUDE block
    out = {}
    for line in text.strip().split("\n"):
        f = line.split()
        out.setdefault(f[0], [])
        out[f[0]].append((f[1], f[2:]))
    return out


def fmt_hex(v):
    return "0x%x" % v


def mach_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


LOOKUPS = """# the constant a table holds under a value, the first one when values are shared
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

# the dynamic tag a table holds under a value, the first one when values are shared
pub fun dyn_name_of(s: *DynSet, value: u64) opt[*DynTag] {
    var i: usize = 0;
    for (i < s.count) {
        if (s.rows[i].value == value) { ret opt[*DynTag].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*DynTag].none{};
}

# the dynamic tag a table holds under a name
pub fun dyn_by_name(s: *DynSet, name: str) opt[*DynTag] {
    var i: usize = 0;
    for (i < s.count) {
        if (str_equals(s.rows[i].name, name)) { ret opt[*DynTag].some{s.rows[i]}; }
        i = i + 1;
    }
    ret opt[*DynTag].none{};
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

# the dynamic tags of walk
fun walk_dyn(s: *DynSet, want: *Expect, n: usize) bool {
    if (s.count != n) { ret false; }
    var i: usize = 0;
    for (i < n) {
        val got: opt[*DynTag] = dyn_by_name(s, want[i].name);
        if (sel got.none) { ret false; }
        if (got.some.value != want[i].value) { ret false; }
        i = i + 1;
    }
    i = 0;
    for (i < n) {
        val row: *DynTag = s.rows[i];
        var j: usize = 0;
        for (j < n) {
            if (j != i && str_equals(s.rows[j].name, row.name)) { ret false; }
            j = j + 1;
        }
        val named: opt[*DynTag] = dyn_by_name(s, row.name);
        if (sel named.none) { ret false; }
        if (named.some != row) { ret false; }
        val valued: opt[*DynTag] = dyn_name_of(s, row.value);
        if (sel valued.none) { ret false; }
        if (valued.some.value != row.value) { ret false; }
        i = i + 1;
    }
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


def canonical(text):
    # the one canonical layout of mach source, as mach fmt writes it
    res = subprocess.run(["mach", "fmt", "-"], input=text, capture_output=True, text=True)
    if res.returncode != 0:
        fail("mach fmt failed: " + res.stdout + res.stderr)
    return res.stdout


def main():
    with open(ELF_H, encoding="utf-8") as f:
        elf = strip_comments(f.read())
    with open(DT_DEF, encoding="utf-8") as f:
        dtdef = f.read()

    env = parse_enums(elf)
    inc = parse_inc(INCLUDE)

    # the value of every named row, and the table it sits in
    rows = {}  # table -> list of (name, value, source)
    seen = {}  # header name -> table, for the exhaustive check
    order = [t for t, _ in TABLES]

    for table, entries in inc.items():
        if table not in order:
            fail("unknown table " + table)
        for source, names in entries:
            source = source.replace("_", " ")
            for n in names:
                if n == "EM_*":
                    continue
                if n not in env:
                    fail("header has no constant " + n)
                if env[n] is None:
                    fail("cannot evaluate " + n)
                if n in seen:
                    fail("constant listed twice: " + n)
                seen[n] = table
                rows.setdefault(table, []).append((n, env[n], source))

    # the machine table takes every EM_ name but the excluded aliases
    for n in env:
        if n.startswith("EM_") and n not in EXCLUDE:
            if env[n] is None:
                fail("cannot evaluate " + n)
            rows.setdefault("EM", []).append((n, env[n], "gABI"))
            seen[n] = "EM"

    # every covered family name is a row, excluded, or an error
    for n in env:
        if n in seen or n in EXCLUDE:
            continue
        if not n.startswith(FAMILIES):
            continue
        if any(n.startswith(p) for p, _ in EXCLUDE_PREFIX):
            continue
        fail("unclassified header constant " + n)

    # dynamic tags
    dt_rows = {}
    dt_macro = {}
    dt_seen = set()
    for macro, name, value in parse_dt(dtdef):
        dt_macro[name] = (macro, value)
    dt_src = {}
    for line in DT_INCLUDE.strip().split("\n"):
        table, name, source, addr = line.split()
        dt_src["DT_" + name] = (table, source.replace("_", " "), addr == "yes")
    for name, (macro, value) in dt_macro.items():
        full = "DT_" + name
        if name in DT_EXCLUDE:
            continue
        if macro in DT_EXCLUDE_MACRO:
            continue
        if full not in dt_src:
            fail("unclassified dynamic tag " + full)
        table, source, addr = dt_src[full]
        if (table == "DT_AARCH64") != (macro == "AARCH64_"):
            fail("dynamic tag " + full + " in the wrong table")
        if (table == "DT_RISCV") != (macro == "RISCV_"):
            fail("dynamic tag " + full + " in the wrong table")
        dt_rows.setdefault(table, []).append((full, value, source, addr))
        dt_seen.add(full)
    for full in dt_src:
        if full not in dt_seen:
            fail("listed dynamic tag not in the header " + full)

    # every header value that a table names must be unique by name within it
    for table in order:
        names = [r[0] for r in rows.get(table, [])]
        if len(names) != len(set(names)):
            fail("duplicate name in " + table)
    for table, _ in DT_TABLES:
        names = [r[0] for r in dt_rows.get(table, [])]
        if len(names) != len(set(names)):
            fail("duplicate name in " + table)

    for table, _ in TABLES:
        if table not in rows:
            fail("empty table " + table)
    for table, _ in DT_TABLES:
        if table not in dt_rows:
            fail("empty table " + table)

    out = []
    out.append("# the ELF constant tables, generated by vendor/llvm/gen-elf-tables.py")
    out.append("# from the LLVM ELF.h and DynamicTags.def pinned in vendor/llvm/REVISION.")
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
    out.append("# a dynamic tag, whose d_un is an address when addr is true")
    out.append("pub rec DynTag {")
    out.append("    name:   str;")
    out.append("    value:  u64;")
    out.append("    source: str;")
    out.append("    addr:   bool;")
    out.append("}")
    out.append("")
    out.append("pub rec DynSet {")
    out.append("    count: usize;")
    out.append("    rows:  **DynTag;")
    out.append("}")
    out.append("")

    for table, desc in TABLES:
        rs = rows[table]
        out.append("# " + desc)
        for name, value, source in rs:
            out.append("pub val %s: Constant = Constant{name: %s, value: %s, source: %s};"
                       % (name, mach_str(name), fmt_hex(value), mach_str(source)))
        out.append("val %s_ROWS: [%d]*Constant = [%d]*Constant{" % (table, len(rs), len(rs)))
        for name, value, source in rs:
            out.append("    ?%s," % name)
        out.append("};")
        out.append("pub val %s: Set = Set{count: %d, rows: ?%s_ROWS[0]};" % (table, len(rs), table))
        out.append("")

    for table, desc in DT_TABLES:
        rs = dt_rows[table]
        out.append("# " + desc)
        for name, value, source, addr in rs:
            out.append("pub val %s: DynTag = DynTag{name: %s, value: %s, source: %s, addr: %s};"
                       % (name, mach_str(name), fmt_hex(value), mach_str(source),
                          "true" if addr else "false"))
        out.append("val %s_ROWS: [%d]*DynTag = [%d]*DynTag{" % (table, len(rs), len(rs)))
        for name, value, source, addr in rs:
            out.append("    ?%s," % name)
        out.append("};")
        out.append("pub val %s: DynSet = DynSet{count: %d, rows: ?%s_ROWS[0]};" % (table, len(rs), table))
        out.append("")

    out.extend(LOOKUPS.split("\n"))
    for table, _ in TABLES:
        out.extend(want_block(table, rows[table]))
    for table, _ in DT_TABLES:
        out.extend(want_block(table, [(n, v, s) for n, v, s, _a in dt_rows[table]]))
    out.extend(TEST_HEAD.split("\n"))
    for table, _ in TABLES:
        out.append("    if (!walk(?%s, ?%s_WANT[0], %d)) { ret 1; }" % (table, table, len(rows[table])))
    for table, _ in DT_TABLES:
        out.append("    if (!walk_dyn(?%s, ?%s_WANT[0], %d)) { ret 1; }" % (table, table, len(dt_rows[table])))
    out.append("    ret 0;")
    out.append("}")
    out.append("")

    text = canonical("\n".join(out) + "\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s: %d tables, %d rows" % (
        OUT, len(TABLES) + len(DT_TABLES),
        sum(len(v) for v in rows.values()) + sum(len(v) for v in dt_rows.values())))


if __name__ == "__main__":
    main()

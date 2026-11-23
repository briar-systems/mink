#!/usr/bin/env python3
# check src/format/spirv/tables.mach against the vendored grammar, apart from gen.
#
# run by hand from anywhere: python3 -I tools/spirv/table.py
# every opcode of the core grammar, every enumerant that takes parameters of every
# kind the table emits, and every instruction of each vendored extended set is
# compared with its row: name, key, and each operand's kind and quantifier in order,
# after the overrides gen applies, which are listed below.
# exits 1 on any difference, printing the rows that differ.

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
VENDOR = os.path.join(ROOT, "gen", "vendor", "spirv-headers")
TABLE = os.path.join(ROOT, "src", "format", "spirv", "tables.mach")
SETS = [
    ("extinst.glsl.std.450.grammar.json", "GLSL.std.450"),
    ("extinst.nonsemantic.shader.debuginfo.100.grammar.json", "NonSemantic.Shader.DebugInfo.100"),
    ("extinst.opencl.std.100.grammar.json", "OpenCL.std"),
]
QUANTIFIER = {"": "one", "?": "optional", "*": "many"}
# the operands gen gives a synthetic kind: (opname, the grammar's kind, the kind gen writes)
OVERRIDES = [("OpSwitch", "PairLiteralIntegerIdRef", "PairLiteralSelectorIdRef")]


def snake(name):
    out = ""
    for i, c in enumerate(name):
        if i > 0 and c.isupper() and (not name[i - 1].isupper() or (i + 1 < len(name) and name[i + 1].islower())):
            out += "_"
        out += c.upper()
    return out


def shapes(operands):
    return [(snake(o["kind"]), QUANTIFIER[o.get("quantifier", "")]) for o in operands]


def value(v):
    return int(v, 16) if isinstance(v, str) else v


def main():
    src = open(TABLE).read()
    section = src[src.index("val OPERANDS"):src.index("val ENUMERANTS")]
    operands = re.findall(r"Operand\{kind: \?K_(\w+), quantifier: Quantifier\.(\w+)\{\}\}", section)

    def slice_of(at, count):
        return operands[int(at):int(at) + int(count)] if at else []

    bad = []
    core = json.load(open(os.path.join(VENDOR, "spirv.core.grammar.json")))
    rows = re.findall(r'Op\{code: (\d+), name: "(\w+)", operands: (?:\?OPERANDS\[(\d+)\]|nil), count: (\d+)\}', src)
    def overridden(i):
        ops = []
        for o in i.get("operands", []):
            kind = o["kind"]
            for op, old, new in OVERRIDES:
                if op == i["opname"] and kind == old:
                    kind = new
            ops.append(dict(o, kind=kind))
        return ops

    want = sorted((i["opcode"], i["opname"], shapes(overridden(i))) for i in core["instructions"])
    got = [(int(c), n, slice_of(a, k)) for c, n, a, k in rows]
    if want != got:
        bad.append("opcodes")

    enumerants = re.findall(r'Enumerant\{value: (\d+), name: "(\w+)", operands: (?:\?OPERANDS\[(\d+)\]|nil), count: (\d+)\}', src)
    enums = {}
    for name, at, count in re.findall(r"val E_(\w+): Enum = Enum\{enumerants: (?:\?ENUMERANTS\[(\d+)\]|nil), count: (\d+)\}", src):
        enums[name] = (int(at) if at else 0, int(count))
    for k in core["operand_kinds"]:
        if k["category"] not in ("ValueEnum", "BitEnum") or snake(k["kind"]) not in enums:
            continue
        at, count = enums[snake(k["kind"])]
        want = sorted((value(e["value"]), e["enumerant"], shapes(e["parameters"])) for e in k["enumerants"] if e.get("parameters"))
        got = [(int(v), n, slice_of(a, c)) for v, n, a, c in enumerants[at:at + count]]
        if want != got:
            bad.append(k["kind"])

    insts = re.findall(r'Instruction\{number: (\d+), name: "([\w.]+)", operands: (?:\?OPERANDS\[(\d+)\]|nil), count: (\d+)\}', src)
    for file, name in SETS:
        grammar = json.load(open(os.path.join(VENDOR, file)))
        m = re.search(r'Set\{name: "%s", instructions: \?INSTRUCTIONS\[(\d+)\], count: (\d+)\}' % re.escape(name), src)
        if not m:
            bad.append(name)
            continue
        at, count = int(m.group(1)), int(m.group(2))
        want = sorted((i["opcode"], i["opname"], shapes(i.get("operands", []))) for i in grammar["instructions"])
        got = [(int(c), n, slice_of(a, k)) for c, n, a, k in insts[at:at + count]]
        if want != got:
            bad.append(name)

    for b in bad:
        print("table.py: rows differ from the grammar: " + b)
    print("table.py: %d opcodes, %d enums, %d sets checked, %d differ" % (len(rows), len(enums), len(SETS), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""compare the fields mink dump and llvm-readobj both print.

usage: crossread.py <mink dump> <llvm-readobj output>

both outputs nest records as `Name {` or `Name [` ... `}` or `]` and print
fields as `Key: value`. a field is identified by its path of enclosing records,
each qualified by its occurrence among its siblings of one name. only fields
present in both outputs are compared. a value llvm-readobj prints as `NAME (N)`
matches mink's value when it equals NAME, N or the number N stands for.
exit 0 when every shared field agrees, 1 on any difference.
a record whose header carries a value in parentheses, as `Flags [ (0x80)`, is a field
named by the record, holding that value, and its rows are that value's flags, which
compare as a set. a line of a record that is neither a field
nor a record, as a range of a code map or an address of a table, is a list row, named
by its record and its position among the record's rows, so two lists compare row by row
and a row one output has and the other lacks is a difference.
"""
import re
import sys

FIELD = re.compile(r"^\s*([^:{}\[\]]+?):\s*(.*?)\s*$")
OPEN = re.compile(r"^\s*(.*?)\s*[{\[](?:\s*(\(.*\)))?\s*$")
CLOSE = re.compile(r"^\s*[}\]]\s*$")


def parse(text):
    fields = {}
    rows = {}
    flags = set()
    stack = [("", {})]
    for line in text.splitlines():
        if CLOSE.match(line):
            if len(stack) > 1:
                stack.pop()
            continue
        m = OPEN.match(line)
        if m and not FIELD.match(line):
            name = m.group(1)
            seen = stack[-1][1]
            seen[name] = seen.get(name, 0) + 1
            if m.group(2) is not None:
                # a record whose header carries a value, as `Flags [ (0x80)`, is a field of that value
                path = "/".join(p for p, _ in stack if p) + f"/{name}#{seen[name]}"
                fields[path] = m.group(2)
            stack.append((f"{name}#{seen[name]}", {}))
            if m.group(2) is not None:
                flags.add("/".join(p for p, _ in stack if p))
            continue
        m = FIELD.match(line)
        if m:
            seen = stack[-1][1]
            key = m.group(1)
            seen[key] = seen.get(key, 0) + 1
            path = "/".join(p for p, _ in stack if p) + f"/{key}#{seen[key]}"
            fields[path] = m.group(2)
            continue
        row = " ".join(line.split())
        if row and len(stack) > 1:
            record = "/".join(p for p, _ in stack if p)
            rows.setdefault(record, []).append(row)
    return fields, rows, flags


def number(s):
    try:
        return int(s, 0)
    except ValueError:
        return None


def forms(s):
    out = {s}
    n = number(s)
    if n is not None:
        out.add(n)
    m = re.match(r"^(.*?)\s*\((.*)\)$", s)
    if m:
        for part in (m.group(1), m.group(2)):
            out.add(part)
            n = number(part)
            if n is not None:
                out.add(n)
    return out


# llvm-readobj prints an image whose load configuration holds CHPE metadata under the
# machine that metadata makes of the one in the file header, so AMD64 reads as ARM64EC
# and ARM64 as ARM64X. mink prints the machine the header holds
MACHINE_RELABEL = {"IMAGE_FILE_MACHINE_AMD64": "IMAGE_FILE_MACHINE_ARM64EC", "IMAGE_FILE_MACHINE_ARM64": "IMAGE_FILE_MACHINE_ARM64X"}


def flag_value(row):
    """a flag row's value, the number in its parentheses, or the row when it has none"""
    m = re.match(r"^.*\((0x[0-9a-fA-F]+|\d+)\)$", row)
    return int(m.group(1), 0) if m else row


def row_form(row):
    """a list row with each number read as its value, so the case of a hex digit means nothing"""
    out = []
    for token in row.split():
        n = number(token)
        out.append(n if n is not None else token)
    return tuple(out)


def relabelled(path, ours, theirs):
    if path != "ImageFileHeader#1/Machine#1":
        return False
    return any(MACHINE_RELABEL.get(f) in forms(theirs) for f in forms(ours))


def main():
    with open(sys.argv[1], errors="replace") as f:
        ours, our_rows, our_flags = parse(f.read())
    with open(sys.argv[2], errors="replace") as f:
        theirs, their_rows, _ = parse(f.read())
    bad = 0
    for path in ours:
        if path in theirs and not (forms(ours[path]) & forms(theirs[path])) and not relabelled(path, ours[path], theirs[path]):
            print(f"  field {path}: mink {ours[path]!r}, llvm-readobj {theirs[path]!r}")
            bad += 1
    # a list both outputs print compares row by row. the rows of a record whose
    # header carries its value name that value's flags, which have no order
    for record, mine in our_rows.items():
        other = their_rows.get(record)
        if other is None:
            continue
        if record in our_flags:
            a, b = sorted(map(str, map(flag_value, mine))), sorted(map(str, map(flag_value, other)))
            if a != b:
                print(f"  flags {record}: mink {mine!r}, llvm-readobj {other!r}")
                bad += 1
            continue
        for i in range(max(len(mine), len(other))):
            a = mine[i] if i < len(mine) else None
            b = other[i] if i < len(other) else None
            if a is None or b is None or row_form(a) != row_form(b):
                print(f"  row {record}#{i + 1}: mink {a!r}, llvm-readobj {b!r}")
                bad += 1
    sys.exit(1 if bad else 0)


main()

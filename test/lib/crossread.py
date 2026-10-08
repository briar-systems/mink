#!/usr/bin/env python3
"""compare the fields mink dump and llvm-readobj both print.

usage: crossread.py <mink dump> <llvm-readobj output>

both outputs nest records as `Name {` or `Name [` ... `}` or `]` and print
fields as `Key: value`. a field is identified by its path of enclosing records,
each qualified by its occurrence among its siblings of one name. only fields
present in both outputs are compared. a value llvm-readobj prints as `NAME (N)`
matches mink's value when it equals NAME, N or the number N stands for.
exit 0 when every shared field agrees, 1 on any difference.
"""
import re
import sys

FIELD = re.compile(r"^\s*([^:{}\[\]]+?):\s*(.*?)\s*$")
OPEN = re.compile(r"^\s*(.*?)\s*[{\[](?:\s*\(.*\))?\s*$")
CLOSE = re.compile(r"^\s*[}\]]\s*$")


def parse(text):
    fields = {}
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
            stack.append((f"{name}#{seen[name]}", {}))
            continue
        m = FIELD.match(line)
        if m:
            seen = stack[-1][1]
            key = m.group(1)
            seen[key] = seen.get(key, 0) + 1
            path = "/".join(p for p, _ in stack if p) + f"/{key}#{seen[key]}"
            fields[path] = m.group(2)
    return fields


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


def main():
    with open(sys.argv[1], errors="replace") as f:
        ours = parse(f.read())
    with open(sys.argv[2], errors="replace") as f:
        theirs = parse(f.read())
    bad = 0
    for path in ours:
        if path in theirs and not (forms(ours[path]) & forms(theirs[path])):
            print(f"  field {path}: mink {ours[path]!r}, llvm-readobj {theirs[path]!r}")
            bad += 1
    sys.exit(1 if bad else 0)


main()

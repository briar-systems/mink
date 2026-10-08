#!/usr/bin/env python3
"""split the members of an ar archive into one file each, for the readobj lane.

usage: python3 -I tools/coff/split-members.py <archive> <dest>

<dest> names a directory that is created and must not exist. each member is written
as <dest>/<archive stem>-<index>-<member name>, so two archives and two members that
share a name never collide. the member names are read from the System V name table
(`//`), and a GNU long name is followed through it. prints the number of members
written. nothing here runs in CI.
"""
import os
import sys


def members(data):
    if data[:8] != b"!<arch>\n":
        sys.exit("split-members: not an ar archive")
    pos = 8
    table = b""
    out = []
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        name = hdr[0:16].rstrip(b" ")
        size = int(hdr[48:58].strip())
        body = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)
        if name == b"/" or name == b"/SYM64/":
            continue
        if name == b"//":
            table = body
            continue
        if name.startswith(b"/") and name[1:].isdigit():
            start = int(name[1:])
            end = table.index(b"/\n", start)
            name = table[start:end]
        elif name.endswith(b"/"):
            name = name[:-1]
        out.append((name.decode("utf-8", "replace"), body))
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python3 -I tools/coff/split-members.py <archive> <dest>")
    archive, dest = sys.argv[1], sys.argv[2]
    if os.path.exists(dest):
        sys.exit("split-members: %s exists, name a fresh directory" % dest)
    os.makedirs(dest)
    stem = os.path.splitext(os.path.basename(archive))[0]
    data = open(archive, "rb").read()
    count = 0
    for name, body in members(data):
        count += 1
        path = os.path.join(dest, "%s-%04d-%s" % (stem, count, name.replace("/", "_")))
        with open(path, "wb") as f:
            f.write(body)
    print(count)


if __name__ == "__main__":
    main()

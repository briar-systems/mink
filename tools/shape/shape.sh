#!/usr/bin/env bash
# the read lane of the ELF, Mach-O, PE and archive readers: every file is read
# through its reader and each structure reports whether it read, with the
# bodies it holds raw, or was refused with its cause. an archive reads each of
# its members and a fat file each of its slices. it runs locally and is never
# part of CI.
#
# usage: bash tools/shape/shape.sh <fuzz> <file or directory>...
#
#   fuzz  the program, out/<host>/debug/bin/fuzz
#   a directory is walked with find -type f | sort, in that order
#
# one line per structure: <path><member or slice>, a tab, then
# `read typed=N raw=N overlaid=N` (ELF), `read commands=N rawcommands=N
# blobs=N rawblobs=N` (Mach-O), `read sections=N typed=N rawbytes=N` (PE),
# `refused <cause> <text>` or `unclaimed`
set -u

[ $# -ge 2 ] || { sed -n '2,/^set/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
fuzz=$1
shift
[ -x "$fuzz" ] || { echo "shape.sh: $fuzz is not built, run: mach build . -a fuzz" >&2; exit 2; }

one() {
    local f=$1 out
    out=$("$fuzz" shape "$f" 2>&1) || { printf '%s\tcrashed exit %s\n' "$f" "$?"; return; }
    printf '%s\n' "$out" | while IFS= read -r l; do printf '%s%s\n' "$f" "$l"; done
}

for p in "$@"; do
    if [ -d "$p" ]; then
        find "$p" -type f | sort | while IFS= read -r f; do one "$f"; done
    else
        one "$p"
    fi
done

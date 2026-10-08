#!/usr/bin/env bash
# the oracle lane of the Mach-O writer: every Mach-O file under the given paths
# is read, written back and compared byte for byte. it runs locally and is
# never part of CI.
#
# usage: bash tools/macho/roundtrip.sh <file or directory>...
#
#   every regular file under each path is handed to the driver in sorted order,
#   which skips what is no Mach-O. a thin file, each slice of a fat file and
#   each member of an archive is one unit, so a fat file or an archive counts
#   once for itself where it is written whole and once for each part it holds.
#   MACH  the compiler, default mach
#
# example:
#   bash tools/macho/roundtrip.sh ~/.local/share/Steam ~/.vscode ~/.cache/zig
#
# prints one line per unit that did not come back and a total, and the exit
# status is 1 when any did not
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
mach=${MACH:-mach}

[ $# -ge 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

(cd "$repo" && "$mach" build . -a roundtrip) >&2 || exit 2
bin=$(ls "$repo"/out/*/debug/bin/roundtrip 2>/dev/null | head -n 1)
[ -n "$bin" ] || { echo "roundtrip: no driver was built" >&2; exit 2; }

find "$@" -type f -print0 | sort -z | xargs -0 -n 400 "$bin" | awk '
    /^FAIL / { print; bad++ }
    /^ok /   { good++ }
    /^total / { skipped += $6 }
    END {
        printf "%d units came back, %d did not, %d files of no Mach-O\n", good, bad, skipped
        exit (bad > 0)
    }'

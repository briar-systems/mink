#!/usr/bin/env bash
# the oracle lane of the link-edit codecs: every link-edit blob of the given
# Mach-O files is cut out, decoded and encoded back, and must come out byte for
# byte. it runs locally and is never part of CI.
#
# usage: bash tools/macho/linkedit.sh <fresh directory> <tag=file>...
#
#   the directory receives the cut blobs and is created if missing, never
#   emptied. each file is named by its tag, so two files never share blobs.
#   MACH  the compiler, default mach
#
# example:
#   bash tools/macho/linkedit.sh out/linkedit-1 sdl="$HOME/lib/libSDL2.dylib" onnx=lib/libonnxruntime.dylib
#
# exit status is the number of blobs that did not come back, 0 when all did
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
mach=${MACH:-mach}

[ $# -ge 2 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
dir=$1
shift
mkdir -p "$dir" || exit 2

(cd "$repo" && "$mach" build . -a linkedit) >&2 || exit 2
bin=$(ls "$repo"/out/*/debug/bin/linkedit 2>/dev/null | head -n 1)
[ -n "$bin" ] || { echo "linkedit: no driver was built" >&2; exit 2; }

for spec in "$@"; do
    python3 -I "$here/cut.py" "$dir" "${spec%%=*}" "${spec#*=}" >/dev/null || exit 2
done

bad=0
total=0
for blob in "$dir"/*; do
    name=${blob##*/}
    case $name in *.seg[0-9]*) continue ;; esac
    kind=${name##*.}
    width=8
    case $name in *.0x7.*) width=4 ;; esac
    total=$((total + 1))
    if ! out=$("$bin" "$kind" "$blob" "$width" "${blob%.chained}.seg" 2>&1); then
        echo "FAIL $name: $out"
        bad=$((bad + 1))
    fi
done
echo "$total blobs, $bad not reproduced"
exit "$bad"

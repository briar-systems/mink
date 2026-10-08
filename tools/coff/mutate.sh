#!/bin/bash
# mutate PE/COFF seeds and read every mutant in a child process, with the hostile
# input driver of test/lib/fuzz.py.
#
# usage: bash tools/coff/mutate.sh <run> <seconds> <seed directory>...
#
# <run> names a fresh directory out/coff-scan/<run>, which must not exist, and
# findings are saved under it. the fuzz program must be built:
# mach build . -a fuzz. the seeds are sniffed by the fuzz program, so they are
# images. nothing here runs in CI.
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
fuzz=${FUZZ:-$repo/out/linux-x86_64/debug/bin/fuzz}
[ $# -ge 3 ] || { echo "usage: bash tools/coff/mutate.sh <run> <seconds> <seed directory>..." >&2; exit 2; }
run=$repo/out/coff-scan/$1
seconds=$2
shift 2
[ -x "$fuzz" ] || { echo "mutate.sh: $fuzz is not built, run: mach build . -a fuzz" >&2; exit 2; }
[ ! -e "$run" ] || { echo "mutate.sh: $run exists, name a fresh run" >&2; exit 2; }
mkdir -p "$run"
python3 -I "$repo/test/lib/fuzz.py" --fuzz "$fuzz" --time "$seconds" --out "$run/findings" "$@"

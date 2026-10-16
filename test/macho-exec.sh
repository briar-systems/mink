#!/usr/bin/env bash
# the lane of the Mach-O executable writer, against ld64.lld. it runs locally
# and is never part of CI.
#
# usage: bash test/macho-exec.sh
#
# the input set is test/macho-exec/*.c, linked into MH_EXECUTE images for arm64
# and x86_64 at macOS 11.0 (rebase opcodes) and 12.0 (chained fixups), each
# with no dylib. test/lib/machoexec.py states the oracle, what it compares and
# the fields it leaves out and why. the program must be built
# (mach build . -a cli), and clang, ld64.lld, llvm-objdump and llvm-readobj
# must be on the path. each run writes into its own directory under
# out/oracle/macho-exec. the exit status is 0 when every image agrees
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -eq 0 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
for tool in clang ld64.lld llvm-objdump llvm-readobj python3; do
    command -v "$tool" >/dev/null 2>&1 || { echo "macho-exec: $tool is not on the path" >&2; exit 2; }
done
mink=$repo/out/linux-x86_64/debug/bin/mink
[ -x "$mink" ] || { echo "macho-exec: build the program first (mach build . -a cli)" >&2; exit 2; }

mkdir -p "$repo/out/oracle/macho-exec" || exit 2
work=$(mktemp -d "$repo/out/oracle/macho-exec/$(date +%Y%m%d-%H%M%S).XXXXXX") || exit 2
echo "== macho-exec ($work)"
python3 "$repo/test/lib/machoexec.py" --mink "$mink" --source "$here/macho-exec" --work "$work"

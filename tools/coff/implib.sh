#!/usr/bin/env bash
# the oracle lane of the import libraries: every member of the given libraries
# is read, and every short import object written back, and the libraries mink
# writes are compared with the ones llvm-lib writes. it runs locally and is
# never part of CI.
#
# usage: bash tools/coff/implib.sh <run> <list>
#
# <run> names a fresh directory out/coff-implib/<run>, which must not exist, and
# <list> is a file of library paths, one per line. enumerate the input set into
# the list first, for example
#   find /usr/lib/wine -type f -name '*.a' -path '*-windows/*' > list.txt
#   find "$HOME/.cache/zig/o" -type f -name '*.lib' >> list.txt
# the driver must be built: mach build . -a implib. llvm-lib, llvm-readobj and
# llvm-nm must be on the path.
#
# read lane, per library: `implib members` reads every archive member through
# the archive reader and the COFF reader, writes each short import object back
# and fails on a difference. what it prints for the short import objects must
# equal what llvm-readobj prints for them (the type, name type, export name
# and symbols), and the name of every long import member must be what a symbol
# `__imp_<name>` that llvm-nm lists as defined derives, as the name type rules say.
#
# build lane, per machine of tools/coff/implib/machines.txt: the library llvm-lib
# writes for tools/coff/implib/sample.def must equal the library `implib build`
# writes for the export list of that machine, byte for byte, every member and
# both linker members included.
#
# the exit status is the number of libraries and builds that differ
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
bin=${IMPLIB:-$repo/out/linux-x86_64/debug/bin/implib}
[ $# -eq 2 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
run=$repo/out/coff-implib/$1
list=$2
[ -x "$bin" ] || { echo "implib.sh: $bin is not built, run: mach build . -a implib" >&2; exit 2; }
[ -f "$list" ] || { echo "implib.sh: no such list: $list" >&2; exit 2; }
[ ! -e "$run" ] || { echo "implib.sh: $run exists, name a fresh run" >&2; exit 2; }
for tool in llvm-lib llvm-readobj llvm-nm; do
    command -v "$tool" >/dev/null 2>&1 || { echo "implib.sh: $tool not found" >&2; exit 2; }
done
mkdir -p "$run"

# the lines llvm-readobj prints for each short import object
theirs() {
    llvm-readobj "$1" 2>/dev/null | awk '
        /^File:/ { keep = 0 }
        /^Format: COFF-import-file/ { keep = 1; print "Format: short import"; next }
        keep && /^(Type|Name type|Export name|Symbol): / { print }'
}

# the same lines of what the driver printed
ours() {
    awk '
        /^Format: / { keep = ($0 == "Format: short import"); if (keep) print; next }
        /^Machine: / { next }
        keep && /^(Type|Name type|Export name|Symbol): / { print }' "$1"
}

# the long import members' names that no defined __imp_ symbol of the library
# backs, once a leading ?, @ or _ and a trailing @ and digits are dropped
unbacked() {
    local out=$1 lib=$2
    llvm-nm --defined-only "$lib" 2>/dev/null | awk '
        NF >= 3 && index($3, "__imp_") == 1 {
            s = substr($3, 7)
            print s
            t = s; sub(/^[?@_]/, "", t); print t
            u = t; sub(/@[0-9]+$/, "", u); print u
        }' | sort -u > "$out.syms"
    sed -n 's/^Name: //p' "$out" | sort -u | comm -23 - "$out.syms"
}

total=0
bad=0
i=0
while IFS= read -r lib; do
    i=$((i + 1))
    out=$run/$i.txt
    total=$((total + 1))
    if ! "$bin" members "$lib" > "$out" 2> "$out.err"; then
        echo "FAIL $lib: the driver failed"
        bad=$((bad + 1))
        continue
    fi
    ours "$out" > "$out.ours"
    theirs "$lib" > "$out.theirs"
    if ! cmp -s "$out.ours" "$out.theirs"; then
        echo "FAIL $lib: short import objects differ from llvm-readobj"
        bad=$((bad + 1))
        continue
    fi
    if [ -n "$(unbacked "$out" "$lib")" ]; then
        echo "FAIL $lib: a long import member names a symbol the library does not define"
        bad=$((bad + 1))
    fi
done < "$list"
echo "read lane: $total libraries, $bad differ"

builds=0
badbuilds=0
while read -r machine hex exports; do
    case $machine in ''|'#'*) continue ;; esac
    builds=$((builds + 1))
    llvm-lib "/def:$here/implib/sample.def" "/out:$run/ref-$machine.lib" "/machine:$machine" || { badbuilds=$((badbuilds + 1)); continue; }
    "$bin" build "$hex" mydll.dll "$here/implib/$exports" "$run/ours-$machine.lib" || { badbuilds=$((badbuilds + 1)); continue; }
    if ! cmp -s "$run/ref-$machine.lib" "$run/ours-$machine.lib"; then
        echo "FAIL build $machine: differs from llvm-lib"
        badbuilds=$((badbuilds + 1))
    fi
done < "$here/implib/machines.txt"
echo "build lane: $builds machines, $badbuilds differ"
exit $((bad + badbuilds))

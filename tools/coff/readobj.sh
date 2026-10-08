#!/usr/bin/env bash
# the oracle lane of the PE/COFF dump: every file of a list is dumped by mink and by
# llvm-readobj, and the fields both print must agree. it runs locally and is never part of
# CI.
#
# usage: bash tools/coff/readobj.sh <run> <list>
#
#   <run>   names a fresh directory out/coff-readobj/<run>, which must not exist
#   <list>  a file of paths, one per line. enumerate the input set into it first, for
#           example
#             find /usr/lib/wine/x86_64-windows /usr/lib/wine/i386-windows -type f \
#               \( -name '*.dll' -o -name '*.exe' -o -name '*.sys' -o -name '*.drv' \) > list.txt
#           or the objects of a directory with find DIR -name '*.obj'
#   MACH      the compiler, default mach
#   READOBJ   the reference tool, default llvm-readobj
#
# llvm-readobj runs with the flags the dump covers: --file-headers, --sections,
# --relocations, --symbols, --coff-imports, --coff-exports, --coff-basereloc,
# --coff-debug-directory, --coff-tls-directory, --coff-load-config, --coff-resources and
# --unwind. each file's mink dump and llvm-readobj output go to the run directory. the
# exit status is the number of files whose shared fields differ or that one side refused.
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
mach=${MACH:-mach}
readobj=${READOBJ:-llvm-readobj}

[ $# -eq 2 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
run=$repo/out/coff-readobj/$1
list=$2
[ ! -e "$run" ] || { echo "readobj.sh: $run exists, name a fresh run" >&2; exit 2; }
[ -f "$list" ] || { echo "readobj.sh: no such list: $list" >&2; exit 2; }
command -v "$readobj" >/dev/null 2>&1 || { echo "readobj.sh: $readobj not found" >&2; exit 2; }

(cd "$repo" && "$mach" build . -a coffdump) >&2 || exit 2
case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    Darwin/arm64)  host_dir=darwin-aarch64 ;;
    Darwin/x86_64) host_dir=darwin-x86_64 ;;
    *) echo "readobj.sh: no mink build for this host" >&2; exit 2 ;;
esac
bin=${COFFDUMP:-$repo/out/$host_dir/debug/bin/coffdump}
[ -x "$bin" ] || { echo "readobj.sh: $bin was not built" >&2; exit 2; }

mkdir -p "$run" || exit 2
total=0; differ=0; ours_refused=0; theirs_refused=0
while IFS= read -r path; do
    [ -n "$path" ] || continue
    total=$((total + 1))
    n=$total
    ours=$run/$n.mink.txt
    theirs=$run/$n.readobj.txt
    if ! "$bin" "$path" > "$ours" 2> "$run/$n.mink.err"; then
        ours_refused=$((ours_refused + 1))
        echo "$path: mink refused: $(head -n 1 "$run/$n.mink.err")"
        continue
    fi
    if ! "$readobj" --file-headers --sections --relocations --symbols --coff-imports \
        --coff-exports --coff-basereloc --coff-debug-directory --coff-tls-directory \
        --coff-load-config --coff-resources --unwind "$path" > "$theirs" 2> "$run/$n.readobj.err"; then
        theirs_refused=$((theirs_refused + 1))
        echo "$path: $readobj refused: $(head -n 1 "$run/$n.readobj.err")"
        continue
    fi
    if ! diff=$(python3 -I "$repo/test/lib/crossread.py" "$ours" "$theirs"); then
        differ=$((differ + 1))
        echo "$path:"
        echo "$diff"
    fi
done < "$list"
echo "files $total, differ $differ, refused by mink $ours_refused, refused by $readobj $theirs_refused"
[ $((differ + ours_refused + theirs_refused)) -eq 0 ]

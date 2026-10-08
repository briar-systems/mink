#!/bin/bash
# read every file of a list with the PE/COFF reader and report how it went.
#
# usage: bash tools/coff/scan.sh <run> <list>
#
# <run> names a fresh directory out/coff-scan/<run>, which must not exist, and
# <list> is a file of paths, one per line. enumerate the input set into the list
# first, for example
#   find /usr/lib/wine /opt/wine-cachyos /usr/share -type f \( -name '*.dll' -o -name '*.exe' -o -name '*.sys' -o -name '*.obj' \) > list.txt
# the fuzz program must be built: mach build . -a fuzz. a file the reader reads
# counts as read, a refusal as refused, and anything else, which includes extents
# that do not tile the file, as a defect. a read file's data directories that
# stayed raw bytes are listed by kind. nothing here runs in CI.
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
fuzz=${FUZZ:-$repo/out/linux-x86_64/debug/bin/fuzz}
[ $# -eq 2 ] || { echo "usage: bash tools/coff/scan.sh <run> <list>" >&2; exit 2; }
run=$repo/out/coff-scan/$1
list=$2
[ -x "$fuzz" ] || { echo "scan.sh: $fuzz is not built, run: mach build . -a fuzz" >&2; exit 2; }
[ -f "$list" ] || { echo "scan.sh: no such list: $list" >&2; exit 2; }
[ ! -e "$run" ] || { echo "scan.sh: $run exists, name a fresh run" >&2; exit 2; }
mkdir -p "$run"
read_n=0; refused=0; defects=0
while IFS= read -r path; do
    "$fuzz" read coff "$path" > /dev/null 2>&1
    case $? in
        0) read_n=$((read_n + 1))
           "$fuzz" held "$path" 2> /dev/null | sed "s|\$| $path|" >> "$run/held.txt" ;;
        1) refused=$((refused + 1)) ;;
        *) defects=$((defects + 1)); echo "$path" >> "$run/defects.txt" ;;
    esac
done < "$list"
{
    echo "read $read_n refused $refused defects $defects"
    echo "held raw by kind:"
    [ -f "$run/held.txt" ] && awk '{print $1}' "$run/held.txt" | sort | uniq -c
} > "$run/summary.txt"
cat "$run/summary.txt"
[ "$defects" -eq 0 ]

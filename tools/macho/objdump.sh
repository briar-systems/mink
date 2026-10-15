#!/usr/bin/env bash
# the reference lane of the Mach-O link-edit decoding: every link-edit entry
# and the unwind info mink dump decodes of the given files is compared with
# what llvm-objdump prints of them, through objdump.py, and must agree. it
# runs locally and is never part of CI.
#
# usage: bash tools/macho/objdump.sh <fresh directory> <file>...
#
#   the directory receives the dumps and is created if missing, never
#   emptied. a fat file is compared slice by slice, each slice cut out with
#   `mink members`. MINK names the program under test, default the debug
#   build, and OBJDUMP the reference tool, default llvm-objdump.
#
# exit status is the number of files with a difference, 0 when every decoded
# entry agrees. a blob mink holds raw is counted and named, never compared.
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
os=$(uname -s | tr '[:upper:]' '[:lower:]')
cpu=$(uname -m)
case $cpu in arm64) cpu=aarch64 ;; esac
mink=${MINK:-$repo/out/$os-$cpu/debug/bin/mink}
objdump=${OBJDUMP:-llvm-objdump}

[ $# -ge 2 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
dir=$1
shift
mkdir -p "$dir" || exit 2
[ -x "$mink" ] || { echo "objdump.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }
command -v "$objdump" >/dev/null 2>&1 || { echo "objdump.sh: $objdump not found" >&2; exit 2; }

bad=0
total=0
n=0

# compare one thin file, writing under <dir>/<n>
one() {
    local file=$1 label=$2 out
    n=$((n + 1))
    out=$dir/$n
    mkdir -p "$out"
    total=$((total + 1))
    if ! "$mink" dump "$file" > "$out/mink.txt" 2> "$out/mink.err"; then
        echo "FAIL $label: $(head -n 1 "$out/mink.err")"
        bad=$((bad + 1))
        return
    fi
    "$objdump" --macho --rebase "$file" > "$out/rebase" 2>/dev/null
    "$objdump" --macho --bind "$file" > "$out/bind" 2>/dev/null
    "$objdump" --macho --lazy-bind "$file" > "$out/lazy" 2>/dev/null
    "$objdump" --macho --weak-bind "$file" > "$out/weak" 2>/dev/null
    "$objdump" --macho --exports-trie "$file" > "$out/exports" 2>/dev/null
    "$objdump" --macho --function-starts "$file" > "$out/starts" 2>/dev/null
    "$objdump" --macho --data-in-code "$file" > "$out/dic" 2>/dev/null
    "$objdump" --macho --unwind-info "$file" > "$out/unwind" 2>/dev/null
    "$objdump" --macho --chained-fixups "$file" > "$out/chained" 2>/dev/null
    local report
    report=$(python3 -I "$here/objdump.py" "$out/mink.txt" "$out")
    local rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "DIFF $label:"
        printf '%s\n' "$report" | sed 's/^/  /'
        bad=$((bad + 1))
    else
        echo "ok   $label$(printf '%s\n' "$report" | grep -c 'held raw' | sed 's/^0$//; s/^\([1-9][0-9]*\)$/ (\1 blobs held raw)/')"
    fi
}

for file in "$@"; do
    kind=$("$mink" sniff "$file" 2>/dev/null) || { echo "SKIP $file: not a format mink reads"; continue; }
    case $kind in
        macho) one "$file" "$file" ;;
        universal)
            members=$dir/members-$((n + 1))
            mkdir -p "$members"
            "$mink" members "$file" -o "$members" > "$members/list" 2>/dev/null || { echo "FAIL $file: members"; bad=$((bad + 1)); continue; }
            while read -r idx name; do
                [ -n "$idx" ] || continue
                one "$members/$idx" "$file($name)"
            done < "$members/list"
            ;;
        *) echo "SKIP $file: $kind" ;;
    esac
done
echo "$total files compared, $bad with differences"
exit "$bad"

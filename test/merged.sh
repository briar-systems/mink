#!/usr/bin/env bash
# the lane of the merged section names. it runs locally and is never part of
# CI.
#
# usage: bash test/merged.sh [corpus]
#
# the input set is every clang object of the native corpus part, found with
# find <corpus>/native/clang-* -name '*.o' (see test/corpus/README.md), whose
# merge.c objects hold strings of 1, 2 and 4 byte elements and constants of 4,
# 8, 16 and 32 bytes. llvm-readobj -S gives each allocated SHF_MERGE section's
# name, type, flags and sh_entsize. the lane checks,
#   - each such section is SHT_PROGBITS, flagged SHF_ALLOC and SHF_MERGE, with
#     SHF_STRINGS for a .rodata.str name and none for a .rodata.cst name
#   - the distinct names and sizes clang writes are the names and sizes of
#     the merged rows of src/format/elf/neutral/naming.mach, one for one
# the reading of those sections back to the merged kinds is the neutral lane's
# (bash test/run.sh --neutral), which converts each corpus object to the
# neutral object and back and compares the two.
#
# corpus defaults to $MINK_CORPUS, then ~/.cache/mink-corpus. llvm-readobj
# must be on the path. the exit status is the number of checks that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -le 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
corpus=${1:-${MINK_CORPUS:-$HOME/.cache/mink-corpus}}
command -v llvm-readobj >/dev/null 2>&1 || { echo "merged: llvm-readobj is not on the path" >&2; exit 2; }
[ -d "$corpus/native" ] || { echo "merged: no native part under $corpus" >&2; exit 2; }

failed=0
check() {
    if [ "$1" = 0 ]; then echo "ok    $2"; else echo "FAIL  $2"; failed=$((failed + 1)); fi
}

# name type entsize strings, one line per allocated merge section of each object
sections() {
    find "$corpus"/native/clang-* -name '*.o' | sort | while read -r f; do
        llvm-readobj -S "$f" | awk '
            /^  Section \{/ { name = ""; type = ""; alloc = 0; merge = 0; strings = 0 }
            /^    Name: /   { name = $2 }
            /^    Type: /   { type = $2 }
            /SHF_ALLOC/     { alloc = 1 }
            /SHF_MERGE/     { merge = 1 }
            /SHF_STRINGS/   { strings = 1 }
            /^    EntrySize: / { if (alloc && merge) print name, type, $2, strings }'
    done
}

found=$(sections)
[ -n "$found" ] || { echo "merged: the corpus holds no allocated merge section" >&2; exit 2; }
count=$(printf '%s\n' "$found" | wc -l)
echo "allocated merge sections: $count, in $(find "$corpus"/native/clang-* -name '*.o' | wc -l) objects"

bad=$(printf '%s\n' "$found" | awk '
    $2 != "SHT_PROGBITS" { print; next }
    $1 ~ /^\.rodata\.str/ && $4 != 1 { print; next }
    $1 ~ /^\.rodata\.cst/ && $4 != 0 { print; next }
    $1 !~ /^\.rodata\.(str|cst)/ { print }')
[ -z "$bad" ] || printf 'unexpected: %s\n' "$bad"
check "$([ -z "$bad" ]; echo $?)" "every merge section is progbits, with SHF_STRINGS exactly for strings"

clang_set=$(printf '%s\n' "$found" | awk '{ print $1, $3 }' | sort -u)
rows_set=$(sed -n 's/.*kind: ?section\.MERGED_[A-Z]*, entsize: \([0-9]*\), type: ?tables\.SHT_PROGBITS, name: opt\[str\]\.some{"\([^"]*\)"}.*/\2 \1/p' \
    "$repo/src/format/elf/neutral/naming.mach" | sort -u)
echo "clang writes:"
printf '%s\n' "$clang_set" | sed 's/^/  /'
diff <(printf '%s\n' "$clang_set") <(printf '%s\n' "$rows_set") >/dev/null
check $? "the names and sizes clang writes are the merged rows, one for one"

exit "$failed"

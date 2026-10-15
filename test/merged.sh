#!/usr/bin/env bash
# the lane of the merged section kinds. it runs locally and is never part of
# CI.
#
# usage: bash test/merged.sh [corpus]
#
# the input set is every clang object of the native part, found with
# find <corpus>/native/clang-* -name '*.o', whose merge.c objects hold strings
# of 1, 2 and 4 byte elements and constants of 4, 8, 16 and 32 bytes, and every
# thin object of the macho part, found with find <corpus>/macho -name '*.o'
# outside macho/fat (see test/corpus/README.md). a part the corpus lacks is
# reported and left out.
#
# the oracle is llvm-readobj -S on each object. the sections it shows as
# entries to merge are, for ELF, every allocated SHF_MERGE section, and for
# Mach-O, every section of type CStringLiterals or 4, 8 or 16ByteLiterals,
# and __TEXT,__ustring, which ld64 merges as UTF-16 strings. from each the lane
# expects one line:
#   section <name> kind <merged strings|merged constants> entsize <n>
#     strings <yes|no> named <section name>
# strings where SHF_STRINGS is set or the type is CStringLiterals or the
# section is __ustring, the entry size from sh_entsize or the type, and named
# the section's own name, its section part for Mach-O. the subject is the
# merged driver (src/cli/merged.mach), which reads the object through mink's
# reader and prints the same line for each section the neutral object gives a
# merged kind, naming it as mink names a nameless section of that kind and
# size. the two sets of lines must be equal, file by file.
#
# corpus defaults to $MINK_CORPUS, then ~/.cache/mink-corpus. the driver must
# be built: mach build . -a merged. llvm-readobj must be on the path. the exit
# status is the number of objects whose lines differ
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -le 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
corpus=${1:-${MINK_CORPUS:-$HOME/.cache/mink-corpus}}

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    *) echo "merged: no driver directory for this host" >&2; exit 2 ;;
esac
driver=${MERGED:-$repo/out/$host_dir/debug/bin/merged}
[ -x "$driver" ] || { echo "merged: build the driver first: mach build . -a merged" >&2; exit 2; }
command -v llvm-readobj >/dev/null 2>&1 || { echo "merged: llvm-readobj is not on the path" >&2; exit 2; }

# the lines llvm-readobj's view of the ELF object `$1` gives
elf_expected() {
    llvm-readobj -S "$1" | awk '
        function emit() {
            if (alloc && merge) {
                kind = strings ? "merged strings" : "merged constants"
                printf "section %s kind %s entsize %s strings %s named %s\n", name, kind, size, strings ? "yes" : "no", name
            }
        }
        /^  Section \{/       { name = ""; alloc = 0; merge = 0; strings = 0; size = 0 }
        /^    Name: /         { name = $2 }
        /SHF_ALLOC/           { alloc = 1 }
        /SHF_MERGE/           { merge = 1 }
        /SHF_STRINGS/         { strings = 1 }
        /^    EntrySize: /    { size = $2; emit() }'
}

# the lines llvm-readobj's view of the Mach-O object `$1` gives
macho_expected() {
    llvm-readobj -S "$1" | awk '
        function emit() {
            kind = ""
            if (type == "CStringLiterals")                         { kind = "merged strings"; size = 1; s = "yes" }
            if (type == "4ByteLiterals")                           { kind = "merged constants"; size = 4; s = "no" }
            if (type == "8ByteLiterals")                           { kind = "merged constants"; size = 8; s = "no" }
            if (type == "16ByteLiterals")                          { kind = "merged constants"; size = 16; s = "no" }
            if (seg == "__TEXT" && name == "__ustring" && type == "Regular") { kind = "merged strings"; size = 2; s = "yes" }
            if (kind != "") printf "section %s,%s kind %s entsize %s strings %s named %s\n", seg, name, kind, size, s, name
        }
        /^  Section \{/   { name = ""; seg = ""; type = "" }
        /^    Name: /     { name = $2 }
        /^    Segment: /  { seg = $2 }
        /^    Type: /     { type = $2; emit() }'
}

failed=0
files=0
sections=0
judge() {
    local f="$1" expected="$2" got rc
    got=$("$driver" "$f" 2>&1)
    rc=$?
    files=$((files + 1))
    sections=$((sections + $(printf '%s' "$expected" | grep -c '^section')))
    if [ $rc -ne 0 ] || [ "$(printf '%s\n' "$got" | sort)" != "$(printf '%s\n' "$expected" | sort)" ]; then
        failed=$((failed + 1))
        echo "FAIL  $f"
        diff <(printf '%s\n' "$expected" | sort) <(printf '%s\n' "$got" | sort) | sed 's/^/      /'
    fi
}

if [ -d "$corpus/native" ]; then
    while read -r f; do judge "$f" "$(elf_expected "$f")"; done < <(find "$corpus"/native/clang-* -name '*.o' | sort)
else
    echo "merged: no native part under $corpus"
fi
if [ -d "$corpus/macho" ]; then
    while read -r f; do judge "$f" "$(macho_expected "$f")"; done < <(find "$corpus/macho" -path "$corpus/macho/fat" -prune -o -name '*.o' -print | sort)
else
    echo "merged: no macho part under $corpus"
fi

echo "objects: $files, sections to merge: $sections, objects that differ: $failed"
exit "$failed"

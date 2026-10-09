#!/bin/bash
# gather the thin Mach-O files under some paths into a corpus for the oracle lanes.
#
# usage: bash tools/macho/gather.sh [--skip <path>]... <run> <path>...
#
# <run> names a fresh directory out/macho-corpus/<run>, which must not exist.
# each --skip path is pruned from the walk and never read, like the corpus itself.
# paths are made absolute first, so a skip matches however either is spelled.
# every other regular file under each path that `mink sniff` names macho is copied to
# <run>/files/<index>-<name>, in sorted order, and <run>/sources.tsv maps each
# copy to the path it came from. a copy keeps the set fixed while the lane runs,
# and a file that cannot be copied is named on stderr and counted.
# then run the lanes over it, for example
#   bash test/run.sh --roundtrip out/macho-corpus/<run>/files
# mink must be built: mach build . -a cli. nothing here runs in CI.
set -u -o pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
mink=${MINK:-$repo/out/linux-x86_64/debug/bin/mink}
usage="usage: bash tools/macho/gather.sh [--skip <path>]... <run> <path>..."
prune=(-path "$repo/out/macho-corpus" -prune)
while [ $# -gt 0 ] && [ "$1" = --skip ]; do
    [ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
    skip=$(realpath -s -m -- "$2" | sed 's/[][*?\\]/\\&/g') || exit 2
    prune+=(-o -path "$skip" -prune)
    shift 2
done
[ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
run=$repo/out/macho-corpus/$1
shift
roots=()
for p in "$@"; do
    root=$(realpath -s -- "$p") || exit 2
    roots+=("$root")
done
[ -x "$mink" ] || { echo "gather.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }
[ ! -e "$run" ] || { echo "gather.sh: $run exists, name a fresh run" >&2; exit 2; }
mkdir -p "$run/files"
: > "$run/sources.tsv"
n=0
lost=0
while IFS= read -r -d '' path; do
    name=$("$mink" sniff "$path" 2> /dev/null) || continue
    [ "$name" = macho ] || continue
    copy=$(printf '%s/files/%06d-%s' "$run" "$((n + 1))" "$(basename "$path")")
    if ! cp -- "$path" "$copy"; then
        lost=$((lost + 1))
        continue
    fi
    n=$((n + 1))
    printf '%s\t%s\n' "${copy#"$run"/}" "$path" >> "$run/sources.tsv"
done < <(find "${roots[@]}" \( "${prune[@]}" \) -o -type f -print0 | sort -z)
echo "$n files gathered into $run/files, $lost could not be copied"

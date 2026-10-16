#!/usr/bin/env bash
# the spec testsuite's modules through the neutral object, judged by wasm2wat
#
#   bash tools/wasm/testsuite.sh <wabt bin> <testsuite> <out> [name]...
#
# writes every module of each named .wast of the testsuite with wast2json
# --enable-threads --enable-function-references, converts each to the neutral
# object and back with `mink neutral -o`, and compares wasm2wat --enable-all's
# listing of the module built back with its listing of the original, and holds
# every module wasm-validate --enable-all passes to pass after the round trip.
# a module the .wast asserts malformed is counted apart, as wasm2wat lists some
# that the specification refuses, and so is a module wasm2wat does not list,
# as an assert_invalid module. with no name, every .wast of the testsuite root is taken.
# MINK names the program under test, default out/<host>/debug/bin/mink. each
# run writes into <out>, which it creates, and deletes nothing. exit 1 when a
# module is refused, lists differently or no longer validates.
set -u
[ $# -ge 3 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
wabt=$1
suite=$2
out=$3
shift 3
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
mink=${MINK:-$repo/out/$(uname -s | tr A-Z a-z)-$(uname -m)/debug/bin/mink}
names=("$@")
if [ ${#names[@]} -eq 0 ]; then
    for f in "$suite"/*.wast; do names+=("$(basename "$f" .wast)"); done
fi
mkdir -p "$out" || exit 2
same=0 differ=0 refused=0 unlisted=0 invalid=0 malformed=0
for n in "${names[@]}"; do
    dir=$out/$n
    mkdir -p "$dir"
    if ! "$wabt/wast2json" --enable-threads --enable-function-references "$suite/$n.wast" -o "$dir/$n.json" >/dev/null 2>"$dir/wast2json.err"; then
        echo "$n: wast2json: $(head -n 1 "$dir/wast2json.err")"
        continue
    fi
    asserted=" $(grep '"type": "assert_malformed"' "$dir/$n.json" | sed -n 's/.*"filename": "\([^"]*\)\.wasm".*/\1/p' | tr '\n' ' ') "
    for f in "$dir"/*.wasm; do
        b=$(basename "$f" .wasm)
        case "$b" in *.built) continue ;; esac
        case "$asserted" in *" $b "*) malformed=$((malformed + 1)); continue ;; esac
        if ! "$wabt/wasm2wat" --enable-all "$f" -o "$dir/$b.wat" 2>/dev/null; then
            unlisted=$((unlisted + 1))
            continue
        fi
        if ! err=$("$mink" neutral "$f" -o "$dir/$b.built.wasm" 2>&1); then
            refused=$((refused + 1))
            echo "  $b: $err"
            continue
        fi
        if "$wabt/wasm-validate" --enable-all "$f" >/dev/null 2>&1 && ! "$wabt/wasm-validate" --enable-all "$dir/$b.built.wasm" >"$dir/$b.invalid" 2>&1; then
            invalid=$((invalid + 1))
            echo "  $b: validates, and the module built back does not: $(head -n 1 "$dir/$b.invalid")"
            continue
        fi
        if ! "$wabt/wasm2wat" --enable-all "$dir/$b.built.wasm" -o "$dir/$b.built.wat" 2>"$dir/$b.err"; then
            differ=$((differ + 1))
            echo "  $b: the module built back does not list: $(head -n 1 "$dir/$b.err")"
            continue
        fi
        if cmp -s "$dir/$b.wat" "$dir/$b.built.wat"; then
            same=$((same + 1))
        else
            differ=$((differ + 1))
            echo "  $b: lists differently"
        fi
    done
done
echo "$same same, $differ differ, $invalid no longer valid, $refused refused, $malformed asserted malformed, $unlisted not listed by wasm2wat"
[ $differ -eq 0 ] && [ $refused -eq 0 ] && [ $invalid -eq 0 ]

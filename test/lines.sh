#!/usr/bin/env bash
# the lane of the neutral line records. it runs locally and is never part of
# CI.
#
# usage: bash test/lines.sh <run>
#
# <run> names a fresh directory out/lines/<run>, which must not exist. the
# drivers must be built: mach build . -a lines -a exec. llvm-dwarfdump,
# llvm-readobj, llvm-nm, llvm-objdump and ld.lld must be on the path.
#
# the input set is the one fixture the lines driver builds through the line
# records (src/cli/lines.mach): a RISC-V 64 _start that saves, calls g with
# R_RISCV_CALL_PLT and returns, and a g that returns, each its own line
# sequence of one text section. the driver writes it as relaxed.o, whose call
# carries R_RISCV_RELAX, and fixed.o, with no marker, links relaxed.o in memory
# into the executable given, and prints the sequences and rows it stated. the
# lane checks,
# reading rows and sequence ends with llvm-dwarfdump --debug-line:
#   - relaxed.o and fixed.o show the stated rows at their section offsets
#   - relaxed.o advances by R_RISCV_ADD16 and R_RISCV_SUB16 pairs, one per
#     advance, and fixed.o by none, its .rela.debug_line holding only the
#     R_RISCV_64 of each sequence start
#   - ld.lld, which relaxes by default, turns the call into one jal, deleting
#     the 4 bytes at offset 8, and the linked rows sit at the relaxed
#     addresses: every row and end at offset 12 or past it 4 bytes lower,
#     from _start's address
#   - mink, linking relaxed.o from the file and the object in memory, shows
#     the stated rows from _start's address, as mink does not relax
#
# the exit status is the number of checks that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    *) echo "lines.sh: the lane runs on a linux host" >&2; exit 2 ;;
esac
lines_bin=${LINES:-$repo/out/$host_dir/debug/bin/lines}
exec_bin=${EXEC:-$repo/out/$host_dir/debug/bin/exec}
[ -x "$lines_bin" ] || { echo "lines.sh: $lines_bin is not built, run: mach build . -a lines" >&2; exit 2; }
[ -x "$exec_bin" ] || { echo "lines.sh: $exec_bin is not built, run: mach build . -a exec" >&2; exit 2; }

out=$repo/out/lines/$1
[ -e "$out" ] && { echo "lines.sh: $out exists, name a fresh run" >&2; exit 2; }
mkdir -p "$out" || exit 2

fails=0
fail() { echo "FAIL $1: $2"; fails=$((fails + 1)); }

# the rows and ends llvm-dwarfdump shows for `$1`, as the driver prints them,
# addresses less `$2`
rows_of() {
    llvm-dwarfdump --debug-line "$1" | awk -v base="$2" '
        /^0x[0-9a-f]+ / {
            at = strtonum($1) - base
            if ($0 ~ /end_sequence/) printf "end 0x%x\n", at
            else printf "row 0x%x %d %d\n", at, $2, $3
        }'
}

# the address of the symbol `$2` in `$1`
address_of() {
    llvm-nm "$1" | awk -v name="$2" '$3 == name { print strtonum("0x" $1) }'
}

# the expected rows of a link that deleted the 4 bytes at offset 8
relaxed_rows() {
    awk '{ at = strtonum($2); if (at >= 12) at -= 4; $2 = sprintf("0x%x", at); print }' "$out/stated"
}

if ! "$lines_bin" "$out" >"$out/printed" 2>"$out/driver.err"; then
    fail driver "the driver is refused: $(cat "$out/driver.err")"
    echo "$fails failed"
    exit $fails
fi
grep -v '^start' "$out/printed" >"$out/stated"

for o in relaxed fixed; do
    rows_of "$out/$o.o" 0 >"$out/$o.rows" || fail "$o.o" "llvm-dwarfdump refuses it"
    cmp -s "$out/$o.rows" "$out/stated" || fail "$o.o" "the rows are not the stated ones, see $out/$o.rows"
    llvm-readobj -r "$out/$o.o" | sed -n '/\.rela\.debug_line {/,/}/p' >"$out/$o.relocs"
done
# an advance is each row or end at another offset than the one before it in
# its sequence
advances=$(awk '$1 == "start" { at = $2; next } $2 != at { n++; at = $2 } END { print n + 0 }' "$out/printed")
[ "$(grep -c R_RISCV_ADD16 "$out/relaxed.relocs")" = "$advances" ] || fail relaxed.o "not one R_RISCV_ADD16 per advance, see $out/relaxed.relocs"
[ "$(grep -c R_RISCV_SUB16 "$out/relaxed.relocs")" = "$advances" ] || fail relaxed.o "not one R_RISCV_SUB16 per advance, see $out/relaxed.relocs"
grep -qE 'R_RISCV_(ADD|SUB|SET)' "$out/fixed.relocs" && fail fixed.o "a fixed section advances by a relocation, see $out/fixed.relocs"
[ "$(grep -c R_RISCV_64 "$out/fixed.relocs")" = 2 ] || fail fixed.o "not one R_RISCV_64 per sequence, see $out/fixed.relocs"

if ld.lld -e _start -o "$out/lld" "$out/relaxed.o" 2>"$out/lld.err"; then
    start=$(address_of "$out/lld" _start)
    llvm-objdump -d "$out/lld" >"$out/lld.dis"
    grep -qE "^ *$(printf '%x' $((start + 4))):.*[[:space:]]jal[[:space:]]" "$out/lld.dis" || fail lld "the call is not relaxed to a jal, see $out/lld.dis"
    rows_of "$out/lld" "$start" >"$out/lld.rows"
    relaxed_rows >"$out/lld.want"
    cmp -s "$out/lld.rows" "$out/lld.want" || fail lld "the rows are not at the relaxed addresses, see $out/lld.rows and $out/lld.want"
else
    fail lld "ld.lld refuses relaxed.o: $(cat "$out/lld.err")"
fi

"$exec_bin" riscv64 "$out/mink" "$out/relaxed.o" 2>"$out/mink.err" || fail mink "mink refuses relaxed.o: $(cat "$out/mink.err")"
for o in mink given; do
    [ -f "$out/$o" ] || continue
    rows_of "$out/$o" "$(address_of "$out/$o" _start)" >"$out/$o.rows"
    cmp -s "$out/$o.rows" "$out/stated" || fail "$o" "the rows are not the stated ones from _start, see $out/$o.rows"
done

echo "$fails failed"
exit $fails

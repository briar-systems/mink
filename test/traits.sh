#!/usr/bin/env bash
# the oracle lane of the ELF trait encodings. it runs locally and is never
# part of CI.
#
# usage: bash test/traits.sh <run>
#
# <run> names a fresh directory out/traits/<run>, which must not exist. the
# driver must be built: mach build . -a traits. llvm-mc, llvm-objdump and
# llvm-readobj must be on the path.
#
# the input set is the two fixtures test/traits/rvc.s, compressed and
# double-float RISC-V code, and test/traits/relax.s, a call and an alignment,
# which llvm-mc assembles with R_RISCV_RELAX and R_RISCV_ALIGN relocations.
# the driver converts each object to the neutral object and builds the file
# from that, stating every axis the file cannot leave unstated, as a producer
# must. for rvc.s llvm-mc assembles it, then the driver writes it stating a
# soft float ABI and RVC, RVE, TSO and the CFI features clear, which gives
# e_flags 0, and from that writes it
# stating the double float ABI and compressed code, as masc's builder states
# them, and the strengthened A6 atomics ABI. from that it writes it once more
# also stating x3 as the global pointer. each time the driver reads the file it wrote back and compares the
# object with the one it built through compare.difference. the lane checks:
#   - every object the driver writes reads back equal to the one it built,
#     traits included, and the driver names each axis that differs
#   - the bare object reads back as soft float, no RVC, with e_flags 0x0
#   - llvm-objdump -d disassembles the stated object with no <unknown>
#   - llvm-readobj -h shows e_flags 0x5 with EF_RISCV_FLOAT_ABI_DOUBLE and
#     EF_RISCV_RVC
#   - llvm-readobj --arch-specific shows Tag_RISCV_atomic_abi 2
#   - llvm-readobj -x shows the x3 object's .riscv.attributes as the psABI lays
#     it out by hand: `A`, the length 19, "riscv", Tag_File and its size 9,
#     then Tag_RISCV_atomic_abi (14) 2 and Tag_RISCV_x3_reg_usage (16) 1. the
#     bytes are compared, as llvm does not know tag 16 and refuses the file
#   - for relax.s, llvm-readobj -r shows the same relocations before and after
#     the driver, R_RISCV_RELAX and R_RISCV_ALIGN naming no symbol,
#     llvm-readobj --symbols shows the same symbols, and a second pass through
#     the driver gives the same bytes as the first. section indexes and name
#     offsets are left out of both comparisons, as the driver lays sections and
#     string tables out in its own order
#
# the exit status is the number of checks that failed
set -u
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
bin=${TRAITS:-$repo/out/linux-x86_64/debug/bin/traits}
[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
run=$repo/out/traits/$1
[ -x "$bin" ] || { echo "traits.sh: $bin is not built, run: mach build . -a traits" >&2; exit 2; }
[ ! -e "$run" ] || { echo "traits.sh: $run exists, name a fresh run" >&2; exit 2; }
for tool in llvm-mc llvm-objdump llvm-readobj; do
    command -v "$tool" >/dev/null 2>&1 || { echo "traits.sh: $tool not found" >&2; exit 2; }
done
mkdir -p "$run"

failed=0
check() {
    if [ "$1" = 0 ]; then echo "ok    $2"; else echo "FAIL  $2"; failed=$((failed + 1)); fi
}

llvm-mc -triple=riscv64 -mattr=+c,+d -target-abi=lp64d -filetype=obj "$here/traits/rvc.s" -o "$run/llvm.o" || exit 2
clear="riscv-rve clear riscv-tso clear riscv-cfi-lp-unlabeled clear riscv-cfi-ss clear riscv-cfi-lp-func-sig clear"
"$bin" "$run/llvm.o" "$run/bare.o" riscv-float-abi soft riscv-rvc clear $clear > "$run/bare.txt" || exit 2
"$bin" "$run/bare.o" "$run/stated.o" riscv-float-abi double riscv-rvc set riscv-atomic-abi a6s $clear > "$run/stated.txt" || exit 2
"$bin" "$run/stated.o" "$run/x3.o" riscv-float-abi double riscv-rvc set riscv-atomic-abi a6s riscv-x3-reg-usage gp $clear > "$run/x3.txt" || exit 2
cat "$run/bare.txt" "$run/stated.txt" "$run/x3.txt"

grep -q '^input riscv64 e_flags 0x0$' "$run/stated.txt" && grep -q '^riscv-float-abi soft$' "$run/stated.txt" && grep -q '^riscv-rvc clear$' "$run/stated.txt"
check $? "the bare object reads back as soft float without rvc"

llvm-objdump -d "$run/stated.o" > "$run/objdump.txt" 2>&1
status=$?
cat "$run/objdump.txt"
[ $status = 0 ] && grep -q 'fadd.d' "$run/objdump.txt" && ! grep -q '<unknown>' "$run/objdump.txt"
check $? "llvm-objdump disassembles every instruction"

llvm-readobj -h "$run/stated.o" > "$run/readobj.txt" 2>&1
status=$?
sed -n '/Flags \[/,/\]/p' "$run/readobj.txt"
[ $status = 0 ] && grep -q 'Flags \[ (0x5)' "$run/readobj.txt" && grep -q 'EF_RISCV_FLOAT_ABI_DOUBLE (0x4)' "$run/readobj.txt" && grep -q 'EF_RISCV_RVC (0x1)' "$run/readobj.txt"
check $? "llvm-readobj shows EF_RISCV_FLOAT_ABI_DOUBLE and EF_RISCV_RVC"

llvm-readobj --arch-specific "$run/stated.o" > "$run/arch.txt" 2>&1
status=$?
grep -A3 'Tag: 14' "$run/arch.txt"
[ $status = 0 ] && grep -A2 'Tag: 14' "$run/arch.txt" | grep -q 'Value: 2' && grep -q 'TagName: atomic_abi' "$run/arch.txt"
check $? "llvm-readobj shows the strengthened A6 atomics ABI"

llvm-readobj -x .riscv.attributes "$run/x3.o" > "$run/x3.hex.txt" 2>&1
status=$?
grep '^0x' "$run/x3.hex.txt"
[ $status = 0 ] && [ "$(grep '^0x' "$run/x3.hex.txt" | cut -c12-46 | tr -d ' \n')" = 411300000072697363760001090000000e021001 ]
check $? "llvm-readobj shows the atomics ABI and x3 usage as the psABI encodes them"

llvm-mc -triple=riscv64 -mattr=+c,+d,+relax -target-abi=lp64d -filetype=obj "$here/traits/relax.s" -o "$run/relax.o" || exit 2
stated="riscv-float-abi double riscv-rvc set $clear"
"$bin" "$run/relax.o" "$run/relax1.o" $stated > "$run/relax1.txt" || exit 2
"$bin" "$run/relax1.o" "$run/relax2.o" $stated > "$run/relax2.txt" || exit 2
for f in relax relax1; do
    llvm-readobj -r "$run/$f.o" | grep -v '^File:' | sed 's/Section ([0-9]*)/Section/' > "$run/$f.rel.txt"
    llvm-readobj --symbols "$run/$f.o" | grep -v '^File:' | sed 's/^\( *Section: [^ ]*\) (0x[0-9a-fA-F]*)$/\1/; s/^\( *Name: [^ ]*\) ([0-9]*)$/\1/' > "$run/$f.syms.txt"
done
grep -q 'R_RISCV_RELAX - ' "$run/relax1.rel.txt" && grep -q 'R_RISCV_ALIGN - ' "$run/relax1.rel.txt" && cmp -s "$run/relax.rel.txt" "$run/relax1.rel.txt" && cmp -s "$run/relax.syms.txt" "$run/relax1.syms.txt"
check $? "llvm-readobj shows the same relocations and symbols, R_RISCV_RELAX and R_RISCV_ALIGN with no symbol"

cmp -s "$run/relax1.o" "$run/relax2.o"
check $? "a second pass through the neutral object gives the same bytes"

cat "$run"/bare.txt "$run"/stated.txt "$run"/x3.txt "$run"/relax1.txt "$run"/relax2.txt | grep '^trait-difference ' | sort | uniq -c
[ "$(grep -c '^difference none$' "$run/bare.txt" "$run/stated.txt" "$run/x3.txt" "$run/relax1.txt" "$run/relax2.txt" | grep -c ':1$')" = 5 ] && ! grep -q '^trait-difference ' "$run/bare.txt" "$run/stated.txt" "$run/x3.txt" "$run/relax1.txt" "$run/relax2.txt"
check $? "every object written reads back equal to the one built, traits included"

exit $failed

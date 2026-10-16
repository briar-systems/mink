#!/usr/bin/env bash
# the lane of the ld64 rules the Mach-O link states for merged sections. it
# runs locally and is never part of CI.
#
# usage: bash test/ld64.sh [ld64]
#
# the input set is the three objects this script writes, assembled by clang
# for x86_64-apple-macos11:
#   a.o  "hello world" and "foo" in __TEXT,__cstring and a literal pointer to
#        "foo" in __DATA,__objc_selrefs, which _main loads
#   b.o  "world" and "foo" in __TEXT,__cstring and literal pointers to "foo"
#        and "world" in __DATA,__objc_selrefs, which _other loads
#   c.o  a literal pointer to "hello world" six bytes on
# the oracle is ld64 itself, run as
#   ld64 -arch x86_64 -platform_version macos 11.0 11.0 -static -e _main a.o b.o -o ab
#   ld64 -arch x86_64 -platform_version macos 11.0 11.0 -static -e _main a.o c.o -o ac
# and read back with llvm-otool -s. the lane checks three rules:
#   tails     ld64 keeps each distinct C string whole: ab's __cstring is
#             "hello world\0foo\0world\0", "world" not shared as the tail of
#             "hello world", so the Mach-O tail rule is off
#   pointers  ld64 keeps one literal pointer per target: ab's
#             __objc_selrefs holds two pointers, to "foo" and to "world",
#             the two inputs' pointers to "foo" merged
#   addends   ld64 links no literal pointer that carries an addend: the
#             link of ac fails, ld64-956.6 stopping on its assertion that a
#             literal pointer has one fixup
#
# ld64 defaults to $LD64. on Linux, tpoechtrager/cctools-port at 904de2a
# builds ld64-956.6 from Apple's sources against libdispatch. clang and llvm-otool must be on the path. each run
# writes into its own directory under out/oracle/ld64. the exit status is the
# number of rules ld64 does not follow as stated
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -le 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
ld64=${1:-${LD64:-}}
[ -n "$ld64" ] && [ -x "$ld64" ] || { echo "ld64: name the ld64 binary, as an argument or in LD64" >&2; exit 2; }
command -v clang >/dev/null 2>&1 || { echo "ld64: clang is not on the path" >&2; exit 2; }
command -v llvm-otool >/dev/null 2>&1 || { echo "ld64: llvm-otool is not on the path" >&2; exit 2; }

run="$repo/out/oracle/ld64/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$run"
echo "ld64: $("$ld64" -v 2>&1 | head -1)"
echo "ld64: run in $run"

cat > "$run/a.s" <<'EOF'
	.section __TEXT,__text,regular,pure_instructions
	.globl _main
_main:
	leaq L_hw(%rip), %rax
	leaq L_sel_a(%rip), %rax
	retq
	.section __TEXT,__cstring,cstring_literals
L_hw:
	.asciz "hello world"
L_foo_a:
	.asciz "foo"
	.section __DATA,__objc_selrefs,literal_pointers,no_dead_strip
L_sel_a:
	.quad L_foo_a
.subsections_via_symbols
EOF
cat > "$run/b.s" <<'EOF'
	.section __TEXT,__text,regular,pure_instructions
	.globl _other
_other:
	leaq L_w(%rip), %rax
	leaq L_sel_b(%rip), %rax
	retq
	.section __TEXT,__cstring,cstring_literals
L_w:
	.asciz "world"
L_foo_b:
	.asciz "foo"
	.section __DATA,__objc_selrefs,literal_pointers,no_dead_strip
L_sel_b:
	.quad L_foo_b
L_sel_w:
	.quad L_w
.subsections_via_symbols
EOF
cat > "$run/c.s" <<'EOF'
	.section __TEXT,__cstring,cstring_literals
L_hw_c:
	.asciz "hello world"
	.section __DATA,__objc_selrefs,literal_pointers,no_dead_strip
L_sel_c:
	.quad L_hw_c+6
.subsections_via_symbols
EOF
for f in a b c; do
    clang -target x86_64-apple-macos11 -c "$run/$f.s" -o "$run/$f.o" || { echo "ld64: clang could not assemble $f.s" >&2; exit 2; }
done

link() {
    "$ld64" -arch x86_64 -platform_version macos 11.0 11.0 -static -e _main "$@" > "$run/$(basename "${@: -1}").log" 2>&1
}

# the bytes of section `$2,$3` of `$1` as one hex string, and its address
section_hex() {
    llvm-otool -s "$2" "$3" "$1" | awk 'NR > 2 { for (i = 2; i <= NF; i++) printf "%s", $i }'
}
section_address() {
    llvm-otool -s "$2" "$3" "$1" | awk 'NR == 3 { print $1 }'
}

# the little endian quad of the 16 hex digits at `$2` in the hex string `$1`
quad() {
    local h=${1:$2:16} v="" i
    for ((i = 14; i >= 0; i -= 2)); do v="$v${h:$i:2}"; done
    printf '%d' "0x$v"
}

failed=0
check() {
    if [ "$2" = "$3" ]; then
        echo "ok    $1"
    else
        failed=$((failed + 1))
        echo "FAIL  $1: expected $2, ld64 gave $3"
    fi
}

if ! link "$run/a.o" "$run/b.o" -o "$run/ab"; then
    echo "ld64: ld64 could not link a.o and b.o, see $run/ab.log" >&2
    exit 2
fi
strings=$(section_hex "$run/ab" __TEXT __cstring)
check tails "68656c6c6f20776f726c6400666f6f00776f726c6400" "$strings"
base=$((0x$(section_address "$run/ab" __TEXT __cstring)))
refs=$(section_hex "$run/ab" __DATA __objc_selrefs)
got="${#refs} hex digits"
if [ "${#refs}" -eq 32 ]; then
    got="foo+$(($(quad "$refs" 0) - base - 12)) world+$(($(quad "$refs" 16) - base - 16))"
fi
check pointers "foo+0 world+0" "$got"

if link "$run/a.o" "$run/c.o" -o "$run/ac"; then
    check addends "refused" "linked"
else
    check addends "refused" "refused"
fi

echo "rules: 3, rules ld64 does not follow: $failed"
exit "$failed"

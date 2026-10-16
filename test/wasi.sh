#!/usr/bin/env bash
# the lane of wasm modules and WASI programs. it runs locally and is never
# part of CI.
#
# usage: bash test/wasi.sh <run>
#
# <run> names a fresh directory out/wasi/<run>, which must not exist. the
# program must be built: mach build . -a cli. clang, rustc with the
# wasm32-wasip1 target, whose self-contained wasi-libc the C program links,
# and wasmtime must be on the path. a tool missing is reported as skipped,
# not failed. wabt is not needed: wasmtime validates every module it compiles.
#
# the lane checks:
#   - gate: test/wasi/gate.c, two functions and one indirect call compiled by
#     clang for wasm32, links into a module with no entry through a function
#     table slot, wasmtime compiles it, and its export run(21) returns 42
#   - c: test/wasi/hello.c links with wasi-libc's crt1-command.o and libc.a
#     into a WASI program that prints "hello from mink" and exits 42, which
#     it does only when its constructors ran lowest priority first
#   - rust: test/wasi/hello.rs, built by rustc with test/wasi/link.sh as its
#     linker, prints "hello from mink" and exits 42
#
# the exit status is the number of checks that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    *) echo "wasi.sh: the lane runs on a linux host" >&2; exit 2 ;;
esac
mink=${MINK:-$repo/out/$host_dir/debug/bin/mink}
[ -x "$mink" ] || { echo "wasi.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }

out=$repo/out/wasi/$1
[ -e "$out" ] && { echo "wasi.sh: $out exists, name a fresh run" >&2; exit 2; }
mkdir -p "$out" || exit 2

fails=0
skips=0
fail() { echo "FAIL $1: $2"; fails=$((fails + 1)); }
skip() { echo "skip $1: $2"; skips=$((skips + 1)); }
link() { "$mink" link "$@" --format wasm --arch wasm32 --system wasi --env preview1; }

# run the WASI program `$2` of check `$1`, which prints "hello from mink" and
# exits 42
program() {
    (cd "$out" && wasmtime run "$2" >"$out/$1.stdout" 2>"$out/$1.stderr")
    status=$?
    [ "$status" = 42 ] || { fail "$1" "exits $status, not 42"; return; }
    [ "$(cat "$out/$1.stdout")" = "hello from mink" ] || { fail "$1" "prints '$(cat "$out/$1.stdout")'"; return; }
    echo "ok   $1"
}

if ! command -v wasmtime >/dev/null; then
    skip all "wasmtime is not on the path"
    echo "$fails failed, $skips skipped"
    exit $fails
fi

if ! command -v clang >/dev/null; then
    skip gate "clang is not on the path"
elif ! clang --target=wasm32 -O1 -c "$here/wasi/gate.c" -o "$out/gate.o" 2>"$out/gate.cc"; then
    skip gate "clang does not compile for wasm32, see $out/gate.cc"
elif ! link "$out/gate.o" -o "$out/gate.wasm" --kind module 2>"$out/gate.link"; then
    fail gate "the link is refused: $(cat "$out/gate.link")"
elif ! wasmtime compile -o "$out/gate.cwasm" "$out/gate.wasm" 2>"$out/gate.valid"; then
    fail gate "wasmtime refuses the module, see $out/gate.valid"
elif [ "$(wasmtime run --invoke run "$out/gate.wasm" 21 2>/dev/null)" != 42 ]; then
    fail gate "run(21) does not return 42"
else
    echo "ok   gate"
fi

libc=
if command -v rustc >/dev/null; then
    libc=$(rustc --print sysroot)/lib/rustlib/wasm32-wasip1/lib/self-contained
fi
if [ -z "$libc" ] || [ ! -f "$libc/libc.a" ]; then
    skip c "rustc's wasm32-wasip1 target and its wasi-libc are not installed"
elif ! command -v clang >/dev/null; then
    skip c "clang is not on the path"
elif ! clang --target=wasm32-wasip1 -O1 -c "$here/wasi/hello.c" -o "$out/hello.o" 2>"$out/c.cc"; then
    skip c "clang does not compile for wasm32-wasip1, see $out/c.cc"
elif ! link "$libc/crt1-command.o" "$out/hello.o" "$libc/libc.a" -o "$out/c.wasm" --kind static 2>"$out/c.link"; then
    fail c "the link is refused: $(cat "$out/c.link")"
else
    program c c.wasm
fi

if [ -z "$libc" ] || [ ! -f "$libc/libc.a" ]; then
    skip rust "rustc's wasm32-wasip1 target is not installed"
elif ! (cd "$out" && MINK=$mink rustc --target wasm32-wasip1 -O -C linker="$here/wasi/link.sh" "$here/wasi/hello.rs" -o "$out/rust.wasm" >"$out/rust.link" 2>&1); then
    fail rust "the build is refused, see $out/rust.link"
else
    program rust rust.wasm
fi

echo "$fails failed, $skips skipped"
exit $fails

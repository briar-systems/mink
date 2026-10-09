#!/usr/bin/env bash
# the lane of static ELF executables. it runs locally and is never part of CI.
#
# usage: bash test/exec.sh <run>
#
# <run> names a fresh directory out/exec/<run>, which must not exist. the
# driver must be built: mach build . -a exec. clang, llvm-readelf and, for
# each architecture the host does not run, qemu-<arch> must be on the path.
#
# the input set is the two fixtures test/exec/start.c, a _start that writes a
# line and exits through the linux system call of each architecture, and
# test/exec/work.c, data, zero fill and read-only data reached from the other
# object, and a function nothing calls. each is compiled freestanding, with
# no C library and a section per function and per object, for x86_64,
# aarch64, riscv64 and riscv32: by clang for every one, and by gcc where the
# host's gcc targets the architecture or <triple>-gcc is on the path. a
# compiler missing for an architecture is reported as skipped, not failed.
# the driver links each pair into a static executable. the lane checks:
#   - the link succeeds
#   - the executable, run natively or under qemu-<arch>, prints
#     "hello from mink" and exits 42
#   - llvm-readelf -l shows a PT_LOAD and PT_GNU_STACK without execute, and no
#     PT_PHDR or PT_INTERP
#   - llvm-readelf --symbols lists work and _start, and not the function
#     nothing calls, which the link collected
#   - on RISC-V, llvm-readelf -A shows the executable's build attributes as
#     the inputs state them, and -l a PT_RISCV_ATTRIBUTES that locates them
#
# the exit status is the number of checks that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64; host_arch=x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64; host_arch=aarch64 ;;
    *) echo "exec.sh: the lane runs on a linux host" >&2; exit 2 ;;
esac
exec_bin=${EXEC:-$repo/out/$host_dir/debug/bin/exec}
[ -x "$exec_bin" ] || { echo "exec.sh: $exec_bin is not built, run: mach build . -a exec" >&2; exit 2; }

out=$repo/out/exec/$1
[ -e "$out" ] && { echo "exec.sh: $out exists, name a fresh run" >&2; exit 2; }
mkdir -p "$out" || exit 2

flags="-O1 -ffreestanding -fno-pic -fno-pie -ffunction-sections -fdata-sections"
fails=0
skips=0

fail() { echo "FAIL $1: $2"; fails=$((fails + 1)); }

# the compiler command of `$1` for the architecture `$2` with triple `$3`,
# empty when the host has none
compiler() {
    case "$1" in
        clang) echo "clang --target=$3" ;;
        gcc)
            if [ "$2" = "$host_arch" ] && command -v gcc >/dev/null; then echo gcc
            elif command -v "$3-gcc" >/dev/null; then echo "$3-gcc"
            fi ;;
    esac
}

for row in x86_64:x86_64-linux-gnu aarch64:aarch64-linux-gnu riscv64:riscv64-linux-gnu riscv32:riscv32-linux-gnu; do
    arch=${row%%:*}
    triple=${row#*:}
    for cc in clang gcc; do
        name=$arch-$cc
        cmd=$(compiler "$cc" "$arch" "$triple")
        if [ -z "$cmd" ]; then
            echo "SKIP $name: no $cc for $triple"
            skips=$((skips + 1))
            continue
        fi
        built=1
        for f in start work; do
            $cmd $flags -c "$here/exec/$f.c" -o "$out/$name-$f.o" 2>"$out/$name-$f.cc" || built=0
        done
        if [ $built = 0 ]; then
            fail "$name" "the fixtures do not compile, see $out/$name-*.cc"
            continue
        fi
        if ! "$exec_bin" "$arch" "$out/$name" "$out/$name-start.o" "$out/$name-work.o" 2>"$out/$name.link"; then
            fail "$name" "the link is refused: $(cat "$out/$name.link")"
            continue
        fi
        chmod +x "$out/$name"
        if [ "$arch" = "$host_arch" ]; then
            "$out/$name" >"$out/$name.stdout"
        else
            "qemu-$arch" "$out/$name" >"$out/$name.stdout"
        fi
        status=$?
        [ "$status" = 42 ] || fail "$name" "exits $status, not 42"
        [ "$(cat "$out/$name.stdout")" = "hello from mink" ] || fail "$name" "prints '$(cat "$out/$name.stdout")'"
        llvm-readelf -l "$out/$name" >"$out/$name.phdrs" || fail "$name" "llvm-readelf -l refuses the executable"
        grep -q '^ *LOAD ' "$out/$name.phdrs" || fail "$name" "no PT_LOAD"
        grep -q '^ *GNU_STACK .* RW  ' "$out/$name.phdrs" || fail "$name" "PT_GNU_STACK is missing or executable"
        grep -qE '^ *(PHDR|INTERP) ' "$out/$name.phdrs" && fail "$name" "a static executable holds PT_PHDR or PT_INTERP"
        llvm-readelf --symbols "$out/$name" >"$out/$name.symbols" || fail "$name" "llvm-readelf --symbols refuses the executable"
        grep -qE ' work$' "$out/$name.symbols" || fail "$name" "the symbol table does not list work"
        grep -qE ' _start$' "$out/$name.symbols" || fail "$name" "the symbol table does not list _start"
        grep -qE ' unused$' "$out/$name.symbols" && fail "$name" "the symbol table lists the collected function"
        case "$arch" in riscv*)
            llvm-readelf -A "$out/$name" >"$out/$name.attributes" || fail "$name" "llvm-readelf -A refuses the executable"
            llvm-readelf -A "$out/$name-start.o" >"$out/$name-start.attributes"
            cmp -s "$out/$name.attributes" "$out/$name-start.attributes" || fail "$name" "the build attributes are not the inputs', see $out/$name.attributes"
            grep -q '^ *ATTRIBUTES ' "$out/$name.phdrs" || fail "$name" "no PT_RISCV_ATTRIBUTES"
        esac
        echo "ok   $name"
    done
done
echo "$fails failed, $skips skipped"
exit $fails

#!/usr/bin/env bash
# objects from gcc and clang for x86-64, x86, aarch64, rv64 and rv32, each with
# and without -ffunction-sections and with and without -fPIC, from src/*.c

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="$CORPUS_DIR/src"
SOURCES="basic data tls"
GCC="${GCC:-gcc}"
CLANG="${CLANG:-clang}"

# arch name, clang target, gcc command with its flags (empty when gcc has no such target here)
ARCHES="x86_64 x86 aarch64 rv64 rv32"
clang_target() {
    case "$1" in
    x86_64) echo x86_64-linux-gnu ;;
    x86) echo i686-linux-gnu ;;
    aarch64) echo aarch64-linux-gnu ;;
    rv64) echo riscv64-linux-gnu ;;
    rv32) echo riscv32-unknown-elf ;;
    esac
}
# a gcc is found by the triple prefix, the host gcc doubles as x86-64 and x86 with -m32
gcc_command() {
    case "$1" in
    x86_64) echo "$GCC" ;;
    x86) echo "$GCC -m32" ;;
    aarch64) echo "${GCC_AARCH64:-aarch64-linux-gnu-gcc}" ;;
    rv64) echo "${GCC_RV64:-riscv64-linux-gnu-gcc}" ;;
    rv32) echo "${GCC_RV32:-riscv32-unknown-elf-gcc}" ;;
    esac
}

begin_part native
note_tool gcc "$GCC" --version
note_tool clang "$CLANG" --version
note flags "-O2 -g -ffreestanding -nostdinc -ffile-prefix-map=<src>=. plus the variant flags"

# build <compiler id> <arch> <compiler command> <extra flags>
build() {
    local id="$1" arch="$2" cc="$3" extra="$4"
    local sect pic
    for sect in nofsec fsec; do
        for pic in nopic pic; do
            local flags="-O2 -g -ffreestanding -nostdinc -ffile-prefix-map=$SRC=. $extra"
            [ "$sect" = fsec ] && flags="$flags -ffunction-sections"
            [ "$pic" = pic ] && flags="$flags -fPIC"
            local dir="native/$id-$arch/$sect-$pic"
            mkdir -p "$CORPUS/$dir"
            local name
            for name in $SOURCES; do
                (cd "$SRC" && $cc $flags -c "$name.c" -o "$CORPUS/$dir/$name.o")
                record "$dir/$name.o" "$id $(tool_version $cc --version | head -n1) $flags $name.c"
            done
        done
    done
}

for arch in $ARCHES; do
    build clang "$arch" "$CLANG" "--target=$(clang_target "$arch")"

    gcc_cmd="$(gcc_command "$arch")"
    if command -v "${gcc_cmd%% *}" >/dev/null 2>&1; then
        build gcc "$arch" "$gcc_cmd" ""
    else
        skipped "gcc $arch" "${gcc_cmd%% *} is not installed"
    fi
done

end_part

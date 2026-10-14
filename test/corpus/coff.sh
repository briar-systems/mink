#!/usr/bin/env bash
# PE/COFF objects, images and import libraries from clang, llvm-mc, lld-link
# and llvm-lib, with nothing of Windows itself:
# - clang objects from src/*.c for x86-64, x86, AArch64 and ARM64EC under the
#   MSVC ABI and x86-64 under MinGW, with and without -ffunction-sections,
#   each with CodeView or DWARF line tables as its ABI writes them
# - a bigobj, llvm-mc over 66000 sections
# - import libraries of short import objects from src/dep.def for every
#   machine llvm-lib names, ARM (ARMNT) and the ARM64X hybrid among them
# - lld-link dlls from src/win.c for x86-64, x86 and AArch64 with a delay
#   loaded import and a load configuration that asks for control flow guard
#   and EH continuation tables and states its code integrity and tail fields
# - an ARM64EC dll, whose load configuration points at the CHPE metadata the
#   link builds, and an ARM64X dll, which carries a dynamic value relocation
#   table
# objects are written with no timestamp, no command line and no path outside
# the corpus, and images with /Brepro, so a rebuild with the same tools is
# byte for byte the same

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="$CORPUS_DIR/src"
SOURCES="basic data tls"
CLANG="${CLANG:-clang}"
LLVM_MC="${LLVM_MC:-llvm-mc}"
LLD_LINK="${LLD_LINK:-lld-link}"
LLVM_LIB="${LLVM_LIB:-llvm-lib}"
CFLAGS="-O2 -g -ffreestanding -nostdinc -fms-extensions -mno-incremental-linker-compatible -ffile-prefix-map=$SRC=. -fdebug-compilation-dir=. -gno-codeview-command-line"

begin_part coff
note_tool clang "$CLANG" --version
note_tool llvm-mc "$LLVM_MC" --version
note_tool lld-link "$LLD_LINK" --version
# llvm-lib is a mode of llvm-ar and states no version of its own
note_tool llvm-lib "${LLVM_AR:-llvm-ar}" --version
note flags "$(hide_src "$SRC" "$CFLAGS") plus the variant flags"

clang_version="clang $(tool_version "$CLANG" --version)"

# compile <dir> <target> <source> <output> <extra flags>: one object, recorded.
# it is built in its own directory, so the object name CodeView records is
# the same from any corpus root
compile() {
    local dir="$1" target="$2" src="$3" out="$4" extra="$5"
    local flags="$CFLAGS --target=$target $extra"
    mkdir -p "$CORPUS/$dir"
    (cd "$CORPUS/$dir" && "$CLANG" $flags -c "$SRC/$src" -o "$out")
    record "$dir/$out" "$clang_version $(hide_src "$SRC" "$flags") $src"
}

# objects, each target with and without one section per function
for target in x86_64-pc-windows-msvc i686-pc-windows-msvc aarch64-pc-windows-msvc arm64ec-pc-windows-msvc x86_64-w64-windows-gnu; do
    for sect in nofsec fsec; do
        extra=""
        [ "$sect" = fsec ] && extra="-ffunction-sections -fdata-sections"
        for name in $SOURCES; do
            compile "coff/clang-$target/$sect" "$target" "$name.c" "$name.obj" "$extra"
        done
    done
done

# a bigobj, which llvm-mc writes once a file holds more sections than a
# regular header counts
dir="coff/llvm-mc/bigobj"
mkdir -p "$CORPUS/$dir"
seq 1 66000 | awk '{ printf ".section .s%d,\"dr\"\n.byte %d\n", $1, $1 % 256 }' |
    "$LLVM_MC" -filetype=obj -triple x86_64-pc-windows-msvc -o "$CORPUS/$dir/big.obj" -
record "$dir/big.obj" "llvm-mc $(tool_version "$LLVM_MC" --version) -filetype=obj -triple x86_64-pc-windows-msvc over 66000 .section directives"

# import libraries of short import objects
dir="coff/llvm-lib"
mkdir -p "$CORPUS/$dir"
lib_version="llvm-lib $(tool_version "${LLVM_AR:-llvm-ar}" --version)"
for machine in x64 x86 arm64 arm arm64ec; do
    "$LLVM_LIB" /nologo "/def:$SRC/dep.def" "/machine:$machine" "/out:$CORPUS/$dir/dep-$machine.lib"
    record "$dir/dep-$machine.lib" "$lib_version /def:<src>/dep.def /machine:$machine"
done
"$LLVM_LIB" /nologo "/def:$SRC/dep.def" "/defArm64Native:$SRC/dep.def" /machine:arm64x "/out:$CORPUS/$dir/dep-arm64x.lib"
record "$dir/dep-arm64x.lib" "$lib_version /def:<src>/dep.def /defArm64Native:<src>/dep.def /machine:arm64x"

# link <dir> <name> <link flags> <inputs...>: one image, recorded with its
# inputs named under the corpus
link_version="lld-link $(tool_version "$LLD_LINK" --version)"
link() {
    local dir="$1" name="$2" flags="$3"
    shift 3
    local inputs=() shown=""
    for f in "$@"; do
        inputs+=("$CORPUS/$f")
        shown="$shown $f"
    done
    "$LLD_LINK" /nologo /Brepro /nodefaultlib /noimplib /dll $flags "/out:$CORPUS/$dir/$name" "${inputs[@]}"
    record "$dir/$name" "$link_version /Brepro /nodefaultlib /noimplib /dll $flags$shown"
}

for pair in x64:x86_64-pc-windows-msvc x86:i686-pc-windows-msvc arm64:aarch64-pc-windows-msvc arm64ec:arm64ec-pc-windows-msvc; do
    machine="${pair%%:*}"
    dir="coff/lld-link/$machine"
    compile "$dir" "${pair#*:}" win.c win.obj ""
done
compile coff/lld-link/arm64ec arm64ec-pc-windows-msvc arm64ec.s arm64ec.obj ""

for machine in x64 x86 arm64; do
    dir="coff/lld-link/$machine"
    link "$dir" win.dll "/machine:$machine /entry:entry /guard:cf /guard:ehcont /delayload:dep.dll" "$dir/win.obj" "coff/llvm-lib/dep-$machine.lib"
done
link coff/lld-link/arm64ec win.dll "/machine:arm64ec /noentry" coff/lld-link/arm64ec/win.obj coff/lld-link/arm64ec/arm64ec.obj coff/llvm-lib/dep-arm64ec.lib
mkdir -p "$CORPUS/coff/lld-link/arm64x"
link coff/lld-link/arm64x win.dll "/machine:arm64x /noentry" coff/lld-link/arm64/win.obj coff/lld-link/arm64ec/win.obj coff/lld-link/arm64ec/arm64ec.obj coff/llvm-lib/dep-arm64x.lib

end_part

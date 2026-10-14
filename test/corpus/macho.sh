#!/usr/bin/env bash
# mach-o objects, dylibs, executables and fat files built on a linux host with
# clang's darwin targets, lld and llvm-lipo, from src/*.c. the objects need no
# sdk, and the images link nothing but themselves, so this part builds wherever
# llvm is installed. macos.sh gathers what apple's own toolchain writes
# usage: macho.sh    (writes to $MINK_CORPUS and manifest/macho.tsv)

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="$CORPUS_DIR/src"
SOURCES="basic data tls"
CLANG="${CLANG:-clang}"
LIPO="${LIPO:-llvm-lipo}"
CFLAGS="-O2 -g -ffreestanding -nostdinc -ffile-prefix-map=$SRC=."
ARCHES="x86_64 arm64 arm64e"
# the architectures lld links images of: arm64e is not linked here
IMAGE_ARCHES="x86_64 arm64"
# the system versions images are built for: dyld info before 12, chained
# fixups asked for at 13
VERSIONS="11 13"

command -v "$CLANG" >/dev/null 2>&1 || die "$CLANG is not installed"

begin_part macho
note_tool clang "$CLANG" --version
note_tool lld "$CLANG" -fuse-ld=lld -Wl,-v -target x86_64-apple-macos11 -nostdlib -dynamiclib -o /dev/null
note_tool lipo "$LIPO" --version
note flags "$(hide_src "$SRC" "$CFLAGS") -target <arch>-apple-macos11 plus the variant flags"

for arch in $ARCHES; do
    dir="macho/$arch"
    for sect in nofsec fsec; do
        for unwind in nounwind unwind; do
            flags="$CFLAGS -target $arch-apple-macos11"
            [ "$sect" = fsec ] && flags="$flags -ffunction-sections"
            [ "$unwind" = unwind ] && flags="$flags -funwind-tables"
            mkdir -p "$CORPUS/$dir/$sect-$unwind"
            shown="$(hide_src "$SRC" "$flags")"
            for name in $SOURCES; do
                (cd "$SRC" && "$CLANG" $flags -c "$name.c" -o "$CORPUS/$dir/$sect-$unwind/$name.o")
                record "$dir/$sect-$unwind/$name.o" "clang $(tool_version "$CLANG" --version) $shown $name.c"
            done
        done
    done
    # an object with an address significance table
    (cd "$SRC" && "$CLANG" $CFLAGS -target "$arch-apple-macos11" -faddrsig -c basic.c -o "$CORPUS/$dir/addrsig.o")
    record "$dir/addrsig.o" "clang $(tool_version "$CLANG" --version) $(hide_src "$SRC" "$CFLAGS") -target $arch-apple-macos11 -faddrsig basic.c"
done

for arch in $IMAGE_ARCHES; do
    dir="macho/$arch"
    # lld resolves a thread-local import at link time, so the externs are linked
    # in, and dynamic lookup covers the runtime thread-local bootstrap
    (cd "$SRC" && "$CLANG" $CFLAGS -target "$arch-apple-macos11" -c externs.c -o "$CORPUS/$dir/externs.o")
    record "$dir/externs.o" "clang $(tool_version "$CLANG" --version) $(hide_src "$SRC" "$CFLAGS") -target $arch-apple-macos11 externs.c"
    objs="$CORPUS/$dir/nofsec-unwind/basic.o $CORPUS/$dir/nofsec-unwind/data.o $CORPUS/$dir/nofsec-unwind/tls.o $CORPUS/$dir/externs.o"
    for v in $VERSIONS; do
        flags="-target $arch-apple-macos$v -fuse-ld=lld -nostdlib -Wl,-undefined,dynamic_lookup"
        [ "$v" = 13 ] && flags="$flags -Wl,-fixup_chains"
        "$CLANG" $flags -dynamiclib -install_name @rpath/libcorpus.dylib $objs -o "$CORPUS/$dir/libcorpus-$v.dylib"
        record "$dir/libcorpus-$v.dylib" "clang $flags -dynamiclib basic.o data.o tls.o from $dir/nofsec-unwind and externs.o"
        "$CLANG" $flags -Wl,-e,_sum $objs -o "$CORPUS/$dir/corpus-$v.exe"
        record "$dir/corpus-$v.exe" "clang $flags -Wl,-e,_sum basic.o data.o tls.o from $dir/nofsec-unwind and externs.o"
    done
done

# fat files pair the thin results of two architectures
mkdir -p "$CORPUS/macho/fat"
for kind in nofsec-unwind/basic.o libcorpus-11.dylib corpus-13.exe; do
    out="macho/fat/$(echo "$kind" | tr / -)"
    "$LIPO" -create "$CORPUS/macho/x86_64/$kind" "$CORPUS/macho/arm64/$kind" -output "$CORPUS/$out"
    record "$out" "llvm-lipo -create macho/x86_64/$kind macho/arm64/$kind"
done
"$LIPO" -create "$CORPUS/macho/x86_64/nofsec-unwind/data.o" "$CORPUS/macho/arm64/nofsec-unwind/data.o" "$CORPUS/macho/arm64e/nofsec-unwind/data.o" \
    -output "$CORPUS/macho/fat/data-3.o"
record macho/fat/data-3.o "llvm-lipo -create x86_64 arm64 arm64e nofsec-unwind/data.o"

end_part

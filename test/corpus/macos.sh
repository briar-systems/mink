#!/usr/bin/env bash
# mach-o objects, dylibs, executables and fat files built by clang
# the owner runs this on a mac and keeps the result outside the repository, because
# a macos sdk may not be redistributed and mostly ships .tbd stubs
# usage: macos.sh    (writes to $MINK_CORPUS and manifest/macos.tsv)

[ "$(uname -s)" = Darwin ] || { echo "macos.sh gathers the mach-o part and must run on macOS" >&2; exit 1; }

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="$CORPUS_DIR/src"
SDK="$(xcrun --sdk macosx --show-sdk-path)"
CFLAGS="-O2 -g -ffreestanding -nostdinc -ffile-prefix-map=$SRC=. -mmacosx-version-min=11.0"
ARCHES="x86_64 arm64 arm64e"

begin_part macos
note xcode "$(xcodebuild -version | tr '\n' ' ')"
note sdk "macosx $(xcrun --sdk macosx --show-sdk-version) $(xcrun --sdk macosx --show-sdk-build-version)"
note_tool clang xcrun clang --version
note_tool ld xcrun ld -v
note flags "$CFLAGS"

for arch in $ARCHES; do
    dir="macos/$arch"
    mkdir -p "$CORPUS/$dir"
    for sect in nofsec fsec; do
        flags="$CFLAGS -arch $arch"
        [ "$sect" = fsec ] && flags="$flags -ffunction-sections"
        mkdir -p "$CORPUS/$dir/$sect"
        for name in basic data tls; do
            (cd "$SRC" && xcrun clang $flags -c "$name.c" -o "$CORPUS/$dir/$sect/$name.o")
            record "$dir/$sect/$name.o" "clang $(tool_version xcrun clang --version) $flags $name.c"
        done
    done

    # the dylib and the executable link the same two objects, tls stays out of the executable
    flags="-O2 -g -ffile-prefix-map=$SRC=. -arch $arch -mmacosx-version-min=11.0 -isysroot $SDK"
    (cd "$SRC" && xcrun clang $flags -dynamiclib -install_name @rpath/libcorpus.dylib \
        -Wl,-undefined,dynamic_lookup basic.c data.c tls.c -o "$CORPUS/$dir/libcorpus.dylib")
    record "$dir/libcorpus.dylib" "clang $flags -dynamiclib -Wl,-undefined,dynamic_lookup basic.c data.c tls.c"
    (cd "$SRC" && xcrun clang $flags -Wl,-undefined,dynamic_lookup -e _sum basic.c data.c \
        -o "$CORPUS/$dir/corpus.exe")
    record "$dir/corpus.exe" "clang $flags -Wl,-undefined,dynamic_lookup -e _sum basic.c data.c"

    # a static library through libtool, the apple archive writer, beside clang's own objects
    (cd "$CORPUS/$dir/nofsec" && xcrun libtool -static -D -o "$CORPUS/$dir/libcorpus.a" basic.o data.o tls.o)
    record "$dir/libcorpus.a" "libtool -static -D basic.o data.o tls.o from $dir/nofsec"
done

# fat files pair the thin results of two architectures
mkdir -p "$CORPUS/macos/fat"
for kind in libcorpus.dylib corpus.exe libcorpus.a nofsec/basic.o; do
    out="macos/fat/$(echo "$kind" | tr / -)"
    xcrun lipo -create "$CORPUS/macos/x86_64/$kind" "$CORPUS/macos/arm64/$kind" -output "$CORPUS/$out"
    record "$out" "lipo -create macos/x86_64/$kind macos/arm64/$kind"
done
xcrun lipo -create -arch x86_64 "$CORPUS/macos/x86_64/libcorpus.dylib" -arch arm64 "$CORPUS/macos/arm64/libcorpus.dylib" \
    -arch arm64e "$CORPUS/macos/arm64e/libcorpus.dylib" -output "$CORPUS/macos/fat/libcorpus-3.dylib"
record macos/fat/libcorpus-3.dylib "lipo -create x86_64 arm64 arm64e libcorpus.dylib"
xcrun lipo -create -segalign x86_64 4 -segalign arm64 E "$CORPUS/macos/x86_64/corpus.exe" "$CORPUS/macos/arm64/corpus.exe" \
    -output "$CORPUS/macos/fat/corpus-aligned.exe"
record macos/fat/corpus-aligned.exe "lipo -create -segalign x86_64 4 -segalign arm64 E corpus.exe"

end_part

#!/usr/bin/env bash
# wasm objects and modules from clang and rustc

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="$CORPUS_DIR/src"
CLANG="${CLANG:-clang}"
RUSTC="${RUSTC:-rustc}"
RUST_TARGET="${RUST_TARGET:-wasm32-wasip1}"
CFLAGS="-O2 -g -ffreestanding -nostdinc -ffile-prefix-map=$SRC=."

begin_part wasm
note_tool clang "$CLANG" --version
note_tool wasm-ld wasm-ld --version
note_tool rustc "$RUSTC" --version
note rust-target "$RUST_TARGET"

# wasm has no tls model in a single threaded module, so tls.c stays native only
for width in 32 64; do
    for sect in nofsec fsec; do
        flags="$CFLAGS --target=wasm$width"
        [ "$sect" = fsec ] && flags="$flags -ffunction-sections"
        dir="wasm/clang-wasm$width/$sect"
        mkdir -p "$CORPUS/$dir"
        shown="$(hide_src "$SRC" "$flags")"
        for name in basic data; do
            (cd "$SRC" && "$CLANG" $flags -c "$name.c" -o "$CORPUS/$dir/$name.o")
            record "$dir/$name.o" "clang $(tool_version "$CLANG" --version) $shown $name.c"
        done
    done
done

# linked modules, one of each shape
for width in 32 64; do
    dir="wasm/clang-wasm$width/linked"
    mkdir -p "$CORPUS/$dir"
    flags="$CFLAGS --target=wasm$width -nostdlib -Wl,--no-entry -Wl,--allow-undefined"
    shown="$(hide_src "$SRC" "$flags")"
    (cd "$SRC" && "$CLANG" $flags -Wl,--export-all basic.c data.c -o "$CORPUS/$dir/exported.wasm")
    record "$dir/exported.wasm" "clang $(tool_version "$CLANG" --version) $shown -Wl,--export-all basic.c data.c"
    (cd "$SRC" && "$CLANG" $flags -Wl,--export-all \
        basic.c data.c -fPIC -shared -o "$CORPUS/$dir/shared.wasm")
    record "$dir/shared.wasm" "clang $(tool_version "$CLANG" --version) $shown -Wl,--export-all basic.c data.c -fPIC -shared"
done

# rustc emits an object, an rlib and a static library of wasm objects, and a module
rflags="--edition 2021 --target $RUST_TARGET -C opt-level=2 -C debuginfo=2 -C panic=abort -C codegen-units=1 --remap-path-prefix=$SRC=."
dir="wasm/rustc"
mkdir -p "$CORPUS/$dir"
rshown="$(hide_src "$SRC" "$rflags")"
(cd "$SRC" && "$RUSTC" $rflags --crate-name corpus --crate-type lib --emit obj -o "$CORPUS/$dir/corpus.o" lib.rs)
record "$dir/corpus.o" "rustc $(tool_version "$RUSTC" --version) $rshown --crate-type lib --emit obj lib.rs"
for kind in rlib staticlib cdylib; do
    case "$kind" in
    rlib) out=libcorpus.rlib ;;
    staticlib) out=libcorpus.a ;;
    cdylib) out=corpus.wasm ;;
    esac
    (cd "$SRC" && "$RUSTC" $rflags --crate-name corpus --crate-type "$kind" -o "$CORPUS/$dir/$out" lib.rs)
    record "$dir/$out" "rustc $(tool_version "$RUSTC" --version) $rshown --crate-type $kind lib.rs"
done

end_part

#!/usr/bin/env bash
# every archive variant from gnu ar and llvm-ar over objects native.sh built

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GNU_AR="${AR:-ar}"
LLVM_AR="${LLVM_AR:-llvm-ar}"
LONG="a_member_name_longer_than_sixteen_bytes"

begin_part archives
note_tool ar "$GNU_AR" --version
note_tool llvm-ar "$LLVM_AR" --version
note members "clang native objects, the nofsec-nopic variants of the named arch"

# member sets are the objects of one arch, plus one copy under a long name
SETS="x86_64 aarch64"
STAGE="$CORPUS/.stage"

# prepare <set>: members in $STAGE/members, short names and one long name
prepare() {
    local src="$CORPUS/native/clang-$1/nofsec-nopic"
    [ -d "$src" ] || die "native.sh has not run, $src is missing"
    rm -rf "$STAGE"
    mkdir -p "$STAGE/members"
    cp "$src"/basic.o "$src"/data.o "$src"/tls.o "$STAGE/members/"
    cp "$src/basic.o" "$STAGE/members/$LONG.o"
}

# make <dir> <label> <ar command> <flags> <members...>
# builds one lib.a, a thin archive keeps copies of its members beside it
make() {
    local dir="$1" label="$2" cmd="$3" flags="$4"
    shift 4
    mkdir -p "$CORPUS/$dir"
    rm -f "$CORPUS/$dir/lib.a"
    if [[ "$flags" == *thin* ]]; then
        local member
        for member in "$@"; do
            cp "$STAGE/members/$member" "$CORPUS/$dir/$member"
            record "$dir/$member" "copied from native/clang-$set/nofsec-nopic"
        done
        (cd "$CORPUS/$dir" && $cmd $flags lib.a "$@")
    else
        (cd "$STAGE/members" && $cmd $flags "$CORPUS/$dir/lib.a" "$@")
    fi
    record "$dir/lib.a" "$label $(tool_version $cmd --version) $flags $*"
}

SHORT="basic.o data.o tls.o"
ALL="basic.o data.o tls.o $LONG.o"

for set in $SETS; do
    prepare "$set"
    base="archives/$set"
    # gnu ar, system v with short names and no symbol table, then gnu with long names
    make "$base/gnu-ar-sysv-short" gnu-ar "$GNU_AR" "rcSD" $SHORT
    make "$base/gnu-ar-gnu-long" gnu-ar "$GNU_AR" "rcsD" $ALL
    make "$base/gnu-ar-thin" gnu-ar "$GNU_AR" "rcsD --thin" $ALL
    # llvm-ar writes every format
    make "$base/llvm-ar-gnu-short" llvm-ar "$LLVM_AR" "--format=gnu rcSD" $SHORT
    make "$base/llvm-ar-gnu-long" llvm-ar "$LLVM_AR" "--format=gnu rcsD" $ALL
    make "$base/llvm-ar-gnu-thin" llvm-ar "$LLVM_AR" "--format=gnu --thin rcsD" $ALL
    make "$base/llvm-ar-bsd-short" llvm-ar "$LLVM_AR" "--format=bsd rcsD" $SHORT
    make "$base/llvm-ar-bsd-long" llvm-ar "$LLVM_AR" "--format=bsd rcsD" $ALL
    make "$base/llvm-ar-darwin-long" llvm-ar "$LLVM_AR" "--format=darwin rcsD" $ALL
done

# llvm-ar writes a 64-bit symbol table (/SYM64/, darwin __.SYMDEF_64) for any
# archive past SYM64_THRESHOLD bytes, so a threshold of zero forces it
set=x86_64
prepare "$set"
for fmt in gnu darwin; do
    dir="archives/$set/llvm-ar-$fmt-sym64"
    mkdir -p "$CORPUS/$dir"
    rm -f "$CORPUS/$dir/lib.a"
    (cd "$STAGE/members" && SYM64_THRESHOLD=0 "$LLVM_AR" --format=$fmt rcsD "$CORPUS/$dir/lib.a" $ALL)
    record "$dir/lib.a" "llvm-ar $(tool_version "$LLVM_AR" --version) SYM64_THRESHOLD=0 --format=$fmt rcsD $ALL"
done
rm -rf "$STAGE"

end_part

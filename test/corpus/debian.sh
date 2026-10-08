#!/usr/bin/env bash
# debian 13 (trixie) objects, archives, shared libraries and executables
# every package is named in debian.pins by version and sha-256 and fetched from
# one snapshot.debian.org instant, so a rebuild fetches the same bytes

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PINS="$CORPUS_DIR/debian.pins"
STAMP="$(awk -F'\t' '$1 == "# snapshot" { print $2 }' "$PINS")"
[ -n "$STAMP" ] || die "no snapshot in $PINS"

CACHE="$CORPUS/.cache/debian"
STAGE="$CORPUS/.stage"

begin_part debian
note snapshot "https://snapshot.debian.org/archive/debian/$STAMP/"
note_tool ar ar --version
note_tool tar tar --version

# only elf files and ar archives are kept, nothing else in a package is corpus
is_binary() {
    case "$(head -c 8 "$1" | od -An -tx1 | tr -d ' \n')" in
    7f454c46*) return 0 ;;
    213c617263683e0a) return 0 ;;
    esac
    return 1
}

while IFS="$TAB" read -r pkg version arch sha path; do
    case "$pkg" in "#"* | "") continue ;; esac
    deb="$CACHE/$(basename "$path")"
    download "https://snapshot.debian.org/archive/debian/$STAMP/$path" "$deb" "$sha"

    rm -rf "$STAGE"
    mkdir -p "$STAGE/x"
    data="$(ar t "$deb" | grep '^data\.tar')"
    ar p "$deb" "$data" >"$STAGE/$data"
    tar -C "$STAGE/x" -xf "$STAGE/$data" --no-same-owner --no-same-permissions

    # a regular file only, the symlinks of a package point at files kept anyway
    find "$STAGE/x" -type f | LC_ALL=C sort | while IFS= read -r file; do
        is_binary "$file" || continue
        rel="${file#"$STAGE/x/"}"
        dest="debian/$arch/$pkg/$rel"
        mkdir -p "$CORPUS/$(dirname "$dest")"
        cp "$file" "$CORPUS/$dest"
        record "$dest" "deb $pkg $version $arch $sha /$rel"
    done
    rm -rf "$STAGE"
done <"$PINS"

end_part

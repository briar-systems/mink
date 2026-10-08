# shared helpers for the corpus scripts, sourced and never run
# stays compatible with bash 3.2 so the macos script can use it

set -eu

CORPUS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORPUS="${MINK_CORPUS:-$HOME/.cache/mink-corpus}"
MANIFEST_DIR="${MINK_MANIFEST_DIR:-$CORPUS_DIR/manifest}"
TAB="$(printf '\t')"

die() {
    echo "corpus: $*" >&2
    exit 1
}

# prints the sha-256 of one file
sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# the line of a tool'"'"'s version output that names the version, or "missing"
tool_version() {
    command -v "$1" >/dev/null 2>&1 || { echo missing; return; }
    local out
    out="$("$@" 2>&1)"
    # the first line that carries a dotted version number
    printf '%s\n' "$out" | grep -m1 -E '[0-9]+\.[0-9]+' | sed 's/^[[:space:]]*//' || printf '%s\n' "$out" | head -n1
}

# begin_part <name>: start the manifest of one corpus part
begin_part() {
    PART="$1"
    mkdir -p "$MANIFEST_DIR" "$CORPUS"
    PART_HEAD="$MANIFEST_DIR/.$PART.head"
    PART_BODY="$MANIFEST_DIR/.$PART.body"
    {
        echo "# mink corpus manifest 1"
        echo "# part${TAB}$PART"
        echo "# host${TAB}$(uname -s) $(uname -m)"
    } >"$PART_HEAD"
    : >"$PART_BODY"
}

# note <key> <value>: a line of provenance in the manifest header
note() {
    echo "# $1${TAB}$2" >>"$PART_HEAD"
}

# note_tool <label> <command...>: record a tool and its exact version
note_tool() {
    local label="$1"
    shift
    note tool "$label${TAB}$(tool_version "$@")"
}

# record <path under the corpus> <source>: add one file to the manifest
record() {
    printf '%s\t%s\t%s\n' "$(sha256 "$CORPUS/$1")" "$1" "$2" >>"$PART_BODY"
}

# skipped <what> <why>: a variant that could not be built here
skipped() {
    note missing "$1${TAB}$2"
    echo "corpus: skipped $1 ($2)" >&2
}

# end_part: write the finished manifest, files sorted by path
end_part() {
    local out="$MANIFEST_DIR/$PART.tsv"
    {
        cat "$PART_HEAD"
        LC_ALL=C sort -t "$TAB" -k2,2 "$PART_BODY"
    } >"$out"
    rm -f "$PART_HEAD" "$PART_BODY"
    echo "corpus: $PART: $(grep -vc '^#' "$out") files"
}

# download <url> <dest> <sha256>: fetch and verify, a cached copy is reused
download() {
    if [ ! -f "$2" ] || [ "$(sha256 "$2")" != "$3" ]; then
        mkdir -p "$(dirname "$2")"
        curl -fsSL --retry 3 -o "$2.part" "$1"
        mv "$2.part" "$2"
    fi
    [ "$(sha256 "$2")" = "$3" ] || die "hash mismatch for $1"
}

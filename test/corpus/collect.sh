#!/usr/bin/env bash
# builds the linux parts of the corpus: debian, native, archives, wasm and macho
# usage: collect.sh [part...]    (no argument builds all of them, in this order)
# the corpus goes to $MINK_CORPUS (default ~/.cache/mink-corpus), never into the repository

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(uname -s)" = Linux ] || { echo "collect.sh builds the linux parts and must run on linux" >&2; exit 1; }

parts=("$@")
[ ${#parts[@]} -gt 0 ] || parts=(debian native archives wasm macho)

for part in "${parts[@]}"; do
    case "$part" in
    debian | native | archives | wasm | macho) bash "$here/$part.sh" ;;
    *) echo "unknown part $part" >&2; exit 1 ;;
    esac
done

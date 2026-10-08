#!/usr/bin/env bash
# checks the corpus against its manifests, every listed file must exist and hash the same
# usage: verify.sh [part...]    (no argument checks every manifest)
# MINK_MANIFEST_DIR names another manifest directory, for comparing a rebuild with the committed one

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

parts=("$@")
if [ ${#parts[@]} -eq 0 ]; then
    for file in "$MANIFEST_DIR"/*.tsv; do
        parts+=("$(basename "$file" .tsv)")
    done
fi

bad=0
for part in "${parts[@]}"; do
    count=0
    while IFS="$TAB" read -r want path _; do
        case "$want" in "#"* | "") continue ;; esac
        count=$((count + 1))
        if [ ! -f "$CORPUS/$path" ]; then
            echo "missing  $path"
            bad=$((bad + 1))
        elif [ "$(sha256 "$CORPUS/$path")" != "$want" ]; then
            echo "differs  $path"
            bad=$((bad + 1))
        fi
    done <"$MANIFEST_DIR/$part.tsv"
    echo "corpus: $part: $count files checked"
done

[ "$bad" -eq 0 ] || die "$bad files do not match"

#!/usr/bin/env bash
# regenerates debian.pins from the trixie index of one snapshot.debian.org instant
# usage: pin-debian.sh <snapshot timestamp, e.g. 20260101T000000Z>
# the pins are the only input debian.sh trusts, so review the diff before committing

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[ $# -eq 1 ] || die "usage: pin-debian.sh <snapshot timestamp>"
STAMP="$1"
ARCHES="amd64 i386 arm64 riscv64"
PACKAGES="libc6 libc6-dev zlib1g zlib1g-dev busybox-static coreutils"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

{
    echo "# snapshot${TAB}$STAMP"
    echo "# package${TAB}version${TAB}arch${TAB}sha256${TAB}pool path"
    for arch in $ARCHES; do
        curl -fsSL "https://snapshot.debian.org/archive/debian/$STAMP/dists/trixie/main/binary-$arch/Packages.xz" |
            xz -dc >"$work/Packages"
        for pkg in $PACKAGES; do
            awk -v RS= -v want="$pkg" -v arch="$arch" -v tab="$TAB" '
                $0 ~ "^Package: " want "\n" || $0 ~ "\nPackage: " want "\n" {
                    n = split($0, lines, "\n")
                    for (i = 1; i <= n; i++) {
                        if (lines[i] ~ /^Version: /) v = substr(lines[i], 10)
                        if (lines[i] ~ /^Filename: /) f = substr(lines[i], 11)
                        if (lines[i] ~ /^SHA256: /) s = substr(lines[i], 9)
                    }
                    print want tab v tab arch tab s tab f
                }' "$work/Packages"
        done
    done
} >"$CORPUS_DIR/debian.pins"

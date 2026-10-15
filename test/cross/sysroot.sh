#!/usr/bin/env bash
# copy the riscv64 linux libc headers and libraries out of the cross image into
# <dir>, which must not exist, for MACH_RISCV64_SYSROOT
#
# usage: test/cross/sysroot.sh <dir>
set -u
. "$(dirname "$0")/lib.sh"
[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[ -e "$1" ] && { echo "sysroot.sh: $1 exists" >&2; exit 2; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "sysroot.sh: build the image first: test/cross/image.sh" >&2; exit 2; }
id=$(docker create "$image") || exit 2
docker cp "$id:/usr/riscv64-linux-gnu" "$1"
rc=$?
docker rm "$id" >/dev/null
exit $rc

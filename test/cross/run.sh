#!/usr/bin/env bash
# run the cross tool this script is called as, from the image test/cross/image.sh
# builds, over the repository and the working directory at their own paths
set -u
. "$(dirname "$(readlink -f "$0")")/lib.sh"
tool=$(basename "$0")
docker image inspect "$image" >/dev/null 2>&1 || { echo "$tool: build the image first: test/cross/image.sh" >&2; exit 2; }
exec docker run --rm -i -u "$(id -u):$(id -g)" -v "$repo:$repo" -v "$PWD:$PWD" -w "$PWD" "$image" "$tool" "$@"

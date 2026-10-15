#!/usr/bin/env bash
# run the cross tool named first, from the image test/cross/image.sh builds, over
# the repository and the working directory at their own paths. test/cross/bin holds
# one script per tool that calls this under its own name
set -u
. "$(dirname "$(readlink -f "$0")")/lib.sh"
tool=$1
shift
docker image inspect "$image" >/dev/null 2>&1 || { echo "$tool: build the image first: test/cross/image.sh" >&2; exit 2; }
exec docker run --rm -i -u "$(id -u):$(id -g)" -v "$repo:$repo" -v "$PWD:$PWD" -w "$PWD" "$image" "$tool" "$@"

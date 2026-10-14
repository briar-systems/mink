#!/usr/bin/env bash
# llvm-readobj for the readobj lane over wasm files
#
# llvm-readobj 23.1 crashes on a wasm file under --all, in the dynamic symbol
# and unwind printers it has no wasm form of, so the lane runs it through this
# wrapper, which replaces --all with the printers that have one and passes
# everything else through:
#
#   READOBJ=tools/wasm/readobj.sh bash test/run.sh --readobj
#
# every other format sees the same flags it would under --all, less the two
# printers, which the lane never compares.
set -u
readobj=${LLVM_READOBJ:-llvm-readobj}
args=()
for arg in "$@"; do
    case "$arg" in
        --all) args+=(--file-header --sections --symbols --relocs) ;;
        *) args+=("$arg") ;;
    esac
done
exec "$readobj" "${args[@]}"

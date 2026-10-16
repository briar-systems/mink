#!/usr/bin/env bash
# the linker rustc runs for wasm32-wasip1: it takes the wasm-ld command line
# rustc writes and links its inputs with mink into a WASI program. MINK names
# the mink to run. an export rustc asks for is kept, as mink exports only what
# the inputs' directives name
set -u
mink=${MINK:?MINK names the mink to run}
inputs=(); dirs=(); libs=(); keep=(); out=
while [ $# -gt 0 ]; do
    case "$1" in
        -flavor|-z) shift 2 ;;
        --export) keep+=(--keep "$2"); shift 2 ;;
        -o) out=$2; shift 2 ;;
        -L) dirs+=("$2"); shift 2 ;;
        -l) libs+=("$2"); shift 2 ;;
        -*) shift ;;
        *) inputs+=("$1"); shift ;;
    esac
done
for l in "${libs[@]}"; do
    for d in "${dirs[@]}"; do
        if [ -f "$d/lib$l.a" ]; then inputs+=("$d/lib$l.a"); break; fi
    done
done
exec "$mink" link "${inputs[@]}" -o "$out" --kind static --format wasm --arch wasm32 --system wasi --env preview1 "${keep[@]}"

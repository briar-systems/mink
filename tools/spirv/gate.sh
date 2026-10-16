#!/usr/bin/env bash
# the SPIR-V link gate: two modules, one exporting f and one importing it by
# LinkageAttributes, linked by mink into a module that spirv-val accepts.
#
# run by hand: bash tools/spirv/gate.sh <mink> <out>
# <mink> is a built mink program and <out> a directory the run writes into.
# each tools/spirv/gate/*.spvasm is assembled with spirv-as for SPIR-V 1.3,
# the two are linked as a module for vulkan, and the result is validated with
# spirv-val in the universal environment of its version. exits 1 when any
# step fails, printing the step.

set -u

if [ $# -ne 2 ]; then
    echo "usage: bash tools/spirv/gate.sh <mink> <out>" >&2
    exit 2
fi
mink=$1
out=$2
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"

step() {
    if ! "$@"; then
        echo "gate: failed: $*" >&2
        exit 1
    fi
}

step spirv-as --target-env spv1.3 "$here/gate/export.spvasm" -o "$out/export.spv"
step spirv-as --target-env spv1.3 "$here/gate/import.spvasm" -o "$out/import.spv"
step "$mink" link --kind module --format spirv --arch spirv --system vulkan -o "$out/linked.spv" "$out/export.spv" "$out/import.spv"
step spirv-val "$out/linked.spv"
echo "gate: spirv-val accepts the linked module"

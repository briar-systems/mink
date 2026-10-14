#!/usr/bin/env bash
# build the cross toolchain image once, and print the version of every tool in it
#
# usage: test/cross/image.sh
#
# put test/cross/bin on PATH to run the tools from the lanes, which take a gcc or
# GNU ld by its triple name (test/exec.sh, test/run.sh --diff), and set
# MACH_RISCV64_SYSROOT to a directory test/cross/sysroot.sh fills for the parity
# lane's riscv64 C probes. the tools see the repository at its own path
set -u
. "$(dirname "$0")/lib.sh"
docker image inspect "$image" >/dev/null 2>&1 || docker build -t "$image" "$here" || exit 2
for t in aarch64-linux-gnu-gcc riscv64-linux-gnu-gcc riscv64-unknown-elf-gcc aarch64-linux-gnu-ld riscv64-linux-gnu-ld riscv64-unknown-elf-ld; do
    printf '%s: %s\n' "$t" "$(docker run --rm "$image" "$t" --version | head -n 1)"
done

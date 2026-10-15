# the cross toolchains of the local lanes: gcc and GNU ld for aarch64 and riscv64
# linux, the riscv64 bare-metal gcc that also targets rv32, and the riscv64 libc
# headers mach's C probes compile against. the base image is pinned by digest and
# the packages come from one snapshot.debian.org instant, so a rebuild installs
# the same versions
FROM debian@sha256:5bc3287b25407c965a30f38e32603dc253a3869e1b12a21ac09bfc27fd8b13ce
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && echo 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20261001T000000Z trixie main' > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu \
        gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu libc6-dev-riscv64-cross \
        gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf \
 && rm -rf /var/lib/apt/lists/*

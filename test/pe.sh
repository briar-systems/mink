#!/usr/bin/env bash
# the lane of PE executables against lld-link. it runs locally and is never
# part of CI.
#
# usage: bash test/pe.sh <run>
#
# <run> names a fresh directory out/pe/<run>, which must not exist. the
# program must be built: mach build . -a cli. clang, lld-link, llvm-readobj
# and python3 must be on the path, and wine for the x86_64 run.
#
# the input set is test/image/pe-reloc/main.c, an entry returning the value
# an absolute data pointer reaches, compiled by clang -O1 for
# x86_64-pc-windows-msvc and aarch64-pc-windows-msvc. mink link links each
# into a PIE for windows, and lld-link links the same object with
# /entry:mainCRTStartup /subsystem:console /nodefaultlib /release
# /timestamp:0. the lane checks:
#   - the link succeeds
#   - llvm-readobj --file-headers --sections --coff-basereloc prints the same
#     for both images, the CheckSum line aside, since lld-link fills the code
#     padding of an x86 image with int3 where mink leaves zeros
#   - the CheckSum each image states is PE Format's checksum of its bytes, as
#     the lane computes it
#   - on x86_64, the image run under wine exits 42. wine runs with no display
#     and a prefix of its own in the run directory
#
# the exit status is the number of checks that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

[ $# -eq 1 ] || { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    *) echo "pe.sh: the lane runs on a linux host" >&2; exit 2 ;;
esac
mink=${MINK:-$repo/out/$host_dir/debug/bin/mink}
[ -x "$mink" ] || { echo "pe.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }

out=$repo/out/pe/$1
[ -e "$out" ] && { echo "pe.sh: $out exists, name a fresh run" >&2; exit 2; }
mkdir -p "$out" || exit 2

src=$here/image/pe-reloc/main.c
fails=0
fail() { echo "FAIL $1: $2"; fails=$((fails + 1)); }

# whether the CheckSum the image `$1` states is PE Format's checksum of it
checksum() {
    python3 -I - "$1" <<'PY'
import struct, sys
d = open(sys.argv[1], "rb").read()
pe = struct.unpack_from("<I", d, 0x3c)[0]
at = pe + 4 + 20 + 64
s = 0
for i in range(0, len(d), 2):
    w = 0 if at <= i < at + 4 else d[i] | ((d[i + 1] if i + 1 < len(d) else 0) << 8)
    s += w
    s = (s & 0xffff) + (s >> 16)
s = (s & 0xffff) + (s >> 16)
sys.exit(0 if (s + len(d)) & 0xffffffff == struct.unpack_from("<I", d, at)[0] else 1)
PY
}

for row in x86_64:x86_64-pc-windows-msvc aarch64:aarch64-pc-windows-msvc; do
    arch=${row%%:*}
    triple=${row#*:}
    obj=$out/$arch.obj
    clang --target="$triple" -O1 -c "$src" -o "$obj" || { fail "$arch" "clang does not compile the input"; continue; }
    if ! "$mink" link "$obj" -o "$out/$arch-mink.exe" --kind pie --format coff --arch "$arch" --system windows --env msvc 2>"$out/$arch.link"; then
        fail "$arch" "the link is refused: $(cat "$out/$arch.link")"
        continue
    fi
    lld-link /entry:mainCRTStartup /subsystem:console /nodefaultlib /release /timestamp:0 "$obj" /out:"$out/$arch-lld.exe" || { fail "$arch" "lld-link does not link the input"; continue; }
    for who in mink lld; do
        llvm-readobj --file-headers --sections --coff-basereloc "$out/$arch-$who.exe" | grep -v -e '^File:' -e 'CheckSum:' >"$out/$arch-$who.txt"
        checksum "$out/$arch-$who.exe" || fail "$arch" "the $who image states a checksum other than its own"
    done
    diff -u "$out/$arch-lld.txt" "$out/$arch-mink.txt" >"$out/$arch.diff" || fail "$arch" "llvm-readobj differs from lld-link's image, see $out/$arch.diff"
    if [ "$arch" = x86_64 ]; then
        env -u DISPLAY -u WAYLAND_DISPLAY WINEPREFIX="$out/wine" WINEDEBUG=-all timeout 300 wine "$out/$arch-mink.exe" >"$out/$arch.run" 2>&1
        status=$?
        [ "$status" = 42 ] || fail "$arch" "the image exits $status under wine, not 42"
    fi
    echo "done $arch"
done

echo "$fails failed"
exit $fails

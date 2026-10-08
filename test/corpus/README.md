# Reference corpus

Real producer output for the local oracle lanes: round trip, cross-reading, hostile
input and differential linking. It is data plus the scripts that rebuild it. The
corpus lives outside the repository, never in CI, and no binary is committed. Only
the scripts, the C and Rust sources they compile, and the manifests are tracked.

The corpus root is `$MINK_CORPUS` (default `~/.cache/mink-corpus`). The manifests are
written to `test/corpus/manifest/` (override with `$MINK_MANIFEST_DIR`).

## Parts

| part | script | host | contents |
|---|---|---|---|
| `debian` | `debian.sh` | Linux | ELF objects, archives, shared libraries and executables of Debian 13 (trixie) for amd64, i386, arm64 and riscv64 |
| `native` | `native.sh` | Linux | gcc and clang objects for x86-64, x86, AArch64, RV64 and RV32, with and without `-ffunction-sections` and `-fPIC` |
| `archives` | `archives.sh` | Linux | GNU ar and llvm-ar archives in every variant |
| `wasm` | `wasm.sh` | Linux | wasm objects and modules from clang and rustc |
| `windows` | `windows.ps1` | Windows | system libraries, MinGW and clang-cl objects and import libraries |
| `macos` | `macos.sh` | macOS | Mach-O objects, dylibs, executables and fat files from clang |

`collect.sh [part...]` runs the Linux parts (all four, in that order, when given
nothing). `windows.ps1` and `macos.sh` refuse to run on any other host and are run by
the owner on those machines. The macOS SDK may not be redistributed, so that part is
gathered on a mac and stored outside the repository, and its manifest records the Xcode
and SDK version.

`verify.sh [part...]` hashes the corpus and compares it with the manifests. To check
that a rebuild reproduces them, build into a second root with a second manifest
directory and compare:

```
MINK_CORPUS=/some/other/root MINK_MANIFEST_DIR=/some/other/manifest ./collect.sh
MINK_CORPUS=/some/other/root ./verify.sh
```

## Pinning

Nothing fetches "latest". `debian.pins` names every package by version and SHA-256 and
the files come from one `snapshot.debian.org` instant, so a rebuild fetches the same
bytes and a hash mismatch aborts. `pin-debian.sh <timestamp>` regenerates the pins, and
the diff is reviewed before it is committed. Compiled parts are deterministic for one
toolchain, and each manifest records the exact tool versions, so a different toolchain
produces different hashes and a new manifest.

## Manifest format

One `manifest/<part>.tsv` per part. Lines starting with `#` are the header, and every
other line is one file, tab separated and sorted by path:

```
<sha256>	<path relative to the corpus root>	<source>
```

The source is the package and version for Debian files, or the tool, its version and
the full flags for built ones. The header records the part, the host, the version of
each tool (`# tool`, label, version) and each variant that could not be built
(`# missing`, what, why).

## Notes

- `src/` holds the fixed C sources and the Rust source. They are freestanding, with no
  headers, so any compiler builds them without a sysroot.
- `archives.sh` builds the 64-bit symbol table archives (gnu `/SYM64/` and darwin
  `__.SYMDEF_64`) with llvm-ar's `SYM64_THRESHOLD=0`, which forces the 64-bit table at
  any size.
- Tools that are not installed are recorded as `# missing` in the manifest, never
  faked. GCC for AArch64, RV64 and RV32 is found by the usual cross prefix
  (`aarch64-linux-gnu-gcc`, `riscv64-linux-gnu-gcc`, `riscv32-unknown-elf-gcc`, or
  `$GCC_AARCH64`, `$GCC_RV64`, `$GCC_RV32`).
- The compiler fuzz seeds under `test/fuzz/corpus/` in mach can be added as a category
  but are not producer output and are not part of this corpus.

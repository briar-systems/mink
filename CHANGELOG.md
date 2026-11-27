# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release groups its entries under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` and `Security`, and marks a breaking change inside the entry.

## [Unreleased]

## [0.2.0] - 2026-11-27

### Added

- `mink.link.write.Written` reports where the image starts in its `Started` tag `entry`: `none` for a kind that starts at no entry, `points` for a format that states its own entry points, `absent` with the spelling of the host's optional entry symbol the link took and nothing defined, and `symbol` with the spelling of the entry symbol it starts at. `mink.link.write.started_dnit` releases the entry alone. Breaking: a `Written` literal states `entry`.

### Changed

- Breaking: `mink.catalog.os.Host` states the system's framework directory as one `frameworks` directory in place of the `sdk_dirs` list and `sdk_dir_count`, and `mink.catalog.os.Search` likewise replaces `frameworks` and `framework_count` with one `frameworks` directory.
- Breaking: `mink.link.input.Claimant.find` returns `res[bool, Fail]`, false for a framework no framework directory the link is given holds, in place of `err[Fail]`.

### Fixed

- A framework a link claim names is linked without an SDK, on a cross build or a current macOS: `mink.link.search` looks for it only in the framework directories the link is given, and otherwise the Mach-O describer makes it from the claim with the install name `/System/Library/Frameworks/<N>.framework/<N>`. A name that is empty or holds a `/` is refused with a note that no given directory holds it.
- mink builds for a host whose `usize` and pointers are 32 bits.

## [0.1.3] - 2026-11-27

### Added

- `mink link` writes its result to stdout as a block in mach's shape, `linked` or `failed` with the target, object count, size, time and output, and leaves out a field with nothing to say.
- `-v` writes a line to stderr as each of the read, resolve, layout and write stages closes, and `-vv` adds a line for each input and the target's facts. `-q` leaves the result out.
- `mink.link.state.observed` runs a link with a `mink.link.readout.Watcher` and tells it as each stage closes, with what the stage made.
- `mink.base.diag.line` reads a sink of notes back one note at a time, and `mink.catalog.target.facts` lists a resolved target's facts.

### Changed

- Diagnostics are blocks with a blank line after each, and a refused link's notes sit inside its block.
- The notes `mink.link.search` writes are headed with `note[mink]`, as every other note is.

## [0.1.2] - 2026-11-26

### Added

- `mink.link.coff.image.unreferenced` tells a front end that a refusal is of a DLL a PE image would load and imports nothing from, as `mink.link.resolve.undefined` does for an undefined reference.

### Fixed

- The refusal of a DLL a PE image would load and imports nothing from names the DLL by its loader name, as the failure's subject, in place of its index among the link's libraries.

## [0.1.1] - 2026-11-25

### Changed

- mink requires mach `^7` in place of `^7.0.0-rc.1`.

### Fixed

- An ELF or COFF object writes all of its DWARF units into one section of each kind, so `objdump -l`, `llvm-objdump -l`, `llvm-dwarfdump --verify` and `readelf` read a relocatable object's line tables and the references between its units. A link that drops an item keeps that item's unit.
- An object has a `.debug_loclists` or `.debug_rnglists` section only where a unit writes a list.
- A DWARF 5 line table lists its first file as both file 0 and file 1, and its rows name file 1, so binutils 2.43 and later read every sequence of a linked `--debug` image without a "bad file number" error.
- Directory 0 of a DWARF 5 line table names the unit's directory, the same string as `DW_AT_comp_dir`, in place of an empty string.

## [0.1.0] - 2026-11-23

Initial release of mink, the linker and object format library for Mach 7 supporting ELF, PE/COFF, Mach-O, archives, WebAssembly, and SPIR-V across Linux, Windows (`x86_64` and `aarch64`), Darwin, WASI, UEFI, and freestanding targets.

### Added

- A PE/COFF link writes a DLL with an export table and base relocations, and its import library. `--interface <path>` saves the library, and an executable links against the DLL through it.
- A Mach-O link writes a dylib with an install name in `LC_ID_DYLIB`, an export trie and `__mh_dylib_header`.
- Export intent lives in the neutral object. A symbol exported by a shared library is stated once, as a format neutral export directive that can also state an ordinal, `NONAME`, `PRIVATE` and a forwarder. ELF and Mach-O export it dynamically, COFF writes it as `.drectve` `/EXPORT` with `,DATA` for data, and wasm exports by the same directive.
- Initial-exec thread-locals link into an ELF shared library.
- COFF carries DWARF line records as `.debug_line` and DWARF frames as `.debug_frame`, beside the Windows function table and unwind data.
- wasm carries DWARF line records, the debugging sections of its inputs, and exports a data symbol as an immutable global holding its address.
- `mink` reads its command line on `std.args`. `link`, `dump`, `sniff` and `formats` are command specs and every help page is generated from them.

### Changed

- **Breaking:** `mink.link.state.link`, `mink.link.search.link` and `mink.link.command.link` return `mink.link.write.Written`, an image with an optional interface file, in place of a `Sink`.
- **Breaking:** `mink.link.command.parse` reads an `args.Invocation`, and `mink.link.command.Command` no longer holds `settings` or `help`.
- **Breaking:** `mink.model.object.Directive` has an `export` field, and the text of an `EXPORT` directive is the name the image exports by, never a format's spec.
- **Breaking:** a shared library refuses every general-dynamic, local-dynamic and descriptor thread-local reference.
- A section stated at an offset is refused on every format but flat.
- Command line refusals and help pages use the layout of `std.args`.
- **Breaking:** `mink link --plan <path>` is `--layout <path>`, and placement is stated only in the layout file. `--tail-merge <on|off>`, `--temporaries <kept|discarded>` and `--require-timing-mode` are the switches `--[no-]tail-merge`, `--[no-]temporaries` and `--[no-]require-timing-mode`.
- A missing input file or library exits 1, and 3 is kept for a file that exists but cannot be read or an output that cannot be written. `mink.base.fail.Cause` gains `missing`.
- Help pages are one line per command and option, with no exit codes.
- The `__mach_dit_required` cell states that marked code needs DIT for its guarantee. The standard library enables the mode where present, continues where absent, and refuses only on `__mach_timing_mode_required`.

### Removed

- **Breaking:** the `--state` flag and the link state file.
- **Breaking:** the flags `--section`, `--region`, `--run-region`, `--load-region`, `--offset`, `--size`, `--fill` and `--base`, which are layout file keys.
- **Breaking:** the output kinds `static-pie` and `bundle`, and `relocatable` outside SPIR-V and `shared` on wasm, which no writer builds. A kind joins the catalog with its writer.

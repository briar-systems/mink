# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release groups its entries under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` and `Security`, and marks a breaking change inside the entry.

## [Unreleased]

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
- The `__mach_dit_required` cell states that marked code needs DIT for its guarantee. The standard library enables the mode where present, continues where absent, and refuses only on `__mach_timing_mode_required`.

### Removed

- **Breaking:** the `--state` flag and the link state file.
- **Breaking:** the output kinds `static-pie` and `bundle`, and `relocatable` outside SPIR-V and `shared` on wasm, which no writer builds. A kind joins the catalog with its writer.

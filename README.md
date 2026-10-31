# mink

<p>
  <a href="https://github.com/briar-systems/mink/actions/workflows/ci.yml"><img src="https://github.com/briar-systems/mink/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/briar-systems/mink?color=FF00FF&labelColor=000000" alt="License"></a>
</p>

**The linker and object format library of the mach toolchain, written in [Mach](https://github.com/briar-systems/mach).**

mink reads relocatable objects, archives and shared libraries from any producer
(GCC, clang, rustc, Go, MSVC, the Apple tools and the mach toolchain alike)
and writes executables, shared libraries, relocatable objects and flat images.
It speaks ELF, PE/COFF, Mach-O, the archive formats, WebAssembly and SPIR-V.
Nothing in mink assumes its input came from mach.

mink is a library first. A compiler links through its API in process, and the
`mink` program is a thin command line over the same API. It reads no
configuration file: everything a link needs comes from the command line, a
link plan or the API.

mink is pre-release. The [changelog](CHANGELOG.md) lists what each version
adds, changes and removes.


## Place in the toolchain

The mach toolchain is four projects, each depending only on the layers below it.

```
mach   language front end
 └ mirl   IR and code generation
    └ masc   assembler
       └ mink   linker and object formats
```

mink is the lowest layer. It depends on nothing but the Mach standard library
and a few protocol packages, such as compression for compressed sections.


## Architecture

- **Format modules.** One module per object format, each holding the complete
  model of its specification with a reader and a writer. Reading an input and
  writing it back gives the same bytes.
- **The neutral object model.** The form the linker works in: sections,
  symbols, relocations and groups, designed against the union of the formats.
  Each format converts its own model to and from it.
- **Catalogs and relocation tables.** Architectures, operating systems and the
  relocations of each format and architecture pair are rows of data. Adding an
  architecture, a format or a system adds rows and a module, never a rewrite.
- **The link phases.** A link is one state record run through fixed phases:
  gather and settle inputs, resolve symbols, collect garbage, reserve
  linker-made tables, lay out, apply relocations and write the image.
- **The program.** `mink link` links, `mink dump` prints any object, archive
  or image as text, `mink sniff` names the format of a file and `mink formats`
  lists every format and what mink does with it. The commands and their help
  pages are one command set built on the standard library's `std.args`, and
  `mink help <command>` prints a page.


## Concurrent links

The library holds no mutable state of its own. Everything a link builds lives
in its state record and comes from the allocator it is given, so one process
may run several links at once, on as many threads, each with its own inputs,
allocator and output. A registry is only read once it is built, so concurrent
links may share one.

What a caller must not share between concurrent links is anything a link
writes: the allocator, the state record or command, the output and notes
sinks, and input bytes a caller still changes while a link reads them.


## Output kinds

`--kind` names what a link builds, and `--format` names the format it is
written in:

| Kind | Formats | What it is |
| --- | --- | --- |
| `static` | ELF, PE/COFF, Mach-O, wasm, flat | an executable at a fixed address that loads no library |
| `dynamic` | ELF, PE/COFF, Mach-O | an executable at a fixed address whose loader binds libraries into it |
| `pie` | ELF, PE/COFF, Mach-O | an executable its loader may place at any address |
| `shared` | ELF, PE/COFF, Mach-O | a shared library: an ELF shared object, a PE DLL or a Mach-O dylib |
| `module` | wasm, SPIR-V | a module that names its own entry points |
| `relocatable` | SPIR-V | an object a later link takes as input |

A kind joins this list when a writer builds it. A kind no writer builds is not
accepted and then refused.

A flat image is the bytes of the sections alone, for firmware and boot code.
It is the only format that places a section at a stated offset
(`--offset section,offset`). Every other format places sections by address,
and a link that states an offset for one is refused.


## Shared libraries

A shared library exports what its inputs say it exports, never a format's own
spelling. A producer states the intent once in the neutral object, as an
export directive naming a symbol. Code or data comes from the symbol's
definition. Each format lowers the intent its own way:

- **ELF** gives the symbol default visibility and exports it from the dynamic
  symbol table.
- **Mach-O** gives it default visibility and exports it through the export
  trie of the dylib. The dylib carries an install name in `LC_ID_DYLIB`, the
  output file name under `@rpath/`.
- **PE/COFF** writes an export table and base relocations. A DLL exports the
  symbols the directives name, with the ordinal, `NONAME`, `PRIVATE` and
  forwarder forms the neutral directive can state.
- **wasm** exports the symbols the directives name by the names they state. A
  data symbol is exported as an immutable global holding its address.

A PE DLL also gets its import library. `--interface path` writes it, and a
later link binds an executable against the DLL through it.

A shared library uses initial-exec thread-locals only. A general-dynamic,
local-dynamic or descriptor reference is refused naming the site. A library
with an initial-exec slot needs static TLS space, so `dlopen` can fail once
that space is spent.


## Debug information

Line records in a neutral object lower to DWARF 5 `.debug_line` on ELF,
Mach-O, PE/COFF and wasm. Frames lower to the format's own unwind data, or to
DWARF call frame information where the object asks for it, as `.eh_frame` on
ELF and `.debug_frame` on COFF. wasm carries line records and the debugging
sections of its inputs into the module as custom sections.

`--compress-debug-sections none|zlib|zstd` compresses the non-alloc debug
sections of the image.


## Constant time

An input that needs data independent timing carries the `__mach_needs_dit`
mark. mink then sets the cell `__mach_dit_required` to one. The cell states a
fact about the code, and the standard library owns the policy. It enables the
mode where the system provides it and continues where it does not.
`--require-timing-mode` sets the separate cell `__mach_timing_mode_required`,
and the standard library refuses to start when that mode is not available.


## Section address symbols

A link of an ELF or flat image defines four families of symbols for the
output sections it holds. They are the startup contract for code that runs
before anything else, such as copying `.data` from where it loads to where it
runs, and they are stable:

- `__run_start_<section>` and `__run_stop_<section>` hold the run address
  (VMA) of the start and end of the output section.
- `__load_start_<section>` and `__load_stop_<section>` hold the load address
  (LMA), where the section's bytes lie in the image.

A section placed in no load region loads where it runs, so its load names
equal its run names. The section name is used as written, so `.data` gives
`__load_start_.data`, which Mach reaches with `#[symbol("__load_start_.data")]`.
A weak reference to a section the image does not hold stays undefined and
reads as 0 on ELF, and a strong one is refused naming the section.

`--region name,origin,length,rwx` states a memory region, `--run-region
section,region` places a section's run address in it and `--load-region
section,region` places its bytes there. For a ROM and a RAM:

```bash
mink link --region rom,0x1000,0x1000,rx --region ram,0x20000000,0x1000,rw \
    --run-region .text,rom --run-region .data,ram --load-region .data,rom \
    start.o main.o -o image --kind static --format elf --arch x86_64 --sys freestanding
```

The startup code copies `__run_stop_.data - __run_start_.data` bytes from
`__load_start_.data` to `__run_start_.data`.


## Building

mink is built with the current release of the [Mach compiler](https://github.com/briar-systems/mach/releases).

```bash
git clone https://github.com/briar-systems/mink.git
cd mink
mach dep pull .
mach build .
```


## License

[MIT](LICENSE)

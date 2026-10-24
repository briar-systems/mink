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

> mink is early work. The design is settled but most of what is described
> here is not built yet.


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
- **The program.** `mink` links from the command line, and `mink dump` prints
  any object, archive or image as text.


## Concurrent links

The library holds no mutable state of its own. Everything a link builds lives
in its state record and comes from the allocator it is given, so one process
may run several links at once, on as many threads, each with its own inputs,
allocator and output. A registry is only read once it is built, so concurrent
links may share one.

What a caller must not share between concurrent links is anything a link
writes: the allocator, the state record or command, the output and notes
sinks, and input bytes a caller still changes while a link reads them.


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
    start.o main.o -o image --kind static --format elf --arch x86_64 --system freestanding
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

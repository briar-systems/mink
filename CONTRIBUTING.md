# Contributing to mink

Thank you for your interest in contributing to mink. Be respectful,
constructive, and professional.


## Building

mink is built with the released Mach compiler that CI pins (`MACH_VERSION` in
`.github/workflows/ci.yml`). Install that release for your host and put `mach`
on `PATH`.

```bash
git clone https://github.com/briar-systems/mink.git
cd mink
mach dep pull .
mach build .
```

The library artifact is `libmink`, whose entry is `src/lib/mink.mach`, and the
program is `mink`, whose entry is `src/bin/mink.mach`. A default Linux x86_64
build writes `out/linux-x86_64/debug/bin/mink`.

Dependencies are `[dep.<name>]` tables in `mach.toml`, and the exact commit of
each is the committed gitlink under `dep/`. There is no lock file.
`mach dep pull .` realizes the committed pins and `mach dep update` moves them.


## Testing and formatting

```bash
mach test .
mach fmt --check .
```

The tree is canonical: `mach fmt .` must leave it unchanged before a pull
request is opened.

Unit tests cover the pieces that can be tested directly, each once, at the
layer that owns it. A table is checked by one test that walks its rows. There
are no regression tests: a defect is fixed in the code, and a test is added
only when the behaviour had no coverage. Checks that need outside tools, such
as agreement with llvm-readobj, round trips over a corpus and validators, run
locally and never in CI. CI builds every target and runs the unit tests.


## Branching

- `main` holds tagged releases only. It takes integration merges from `dev`.
- `dev` is the integration branch and the target of every pull request.
- `feat/<issue>` and `fix/<issue>` branch off `dev` and return to it.
- `hotfix/<issue>` branches off `main` and merges into both `main` and `dev`.


## Commits

Commits are small, self-contained, and conventional. The issue number is the
scope:

```
fix(#1234): brief description

Longer explanation if needed.
```

The types are `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`,
`ci`, and `perf`. A breaking change marks the type with `!` before the colon:
`feat(#139)!: brief description`. A change with no issue uses `chore: ...` with
no scope, and a release commit is `chore(release): <version>`.


## Pull requests

- Open as a draft targeting `dev`, and mark it ready when it is done.
- Link the issue with `Closes #N`.
- Leave `CHANGELOG.md` alone. The changelog is written from the merged
  commits when `dev` is released to `main`.
- Say briefly what changed and which checks you ran. Every pull request runs
  CI on linux. To test a windows or darwin change before it merges, dispatch
  CI on the branch with `-f runners='["macos-15"]'` or another runner.
- Merge with a merge commit. Never rebase or fast-forward.
- When the target is not the default branch, close the linked issue by hand
  after the merge.


## Issues

File issues through the templates and label them across these sets:

- SemVer magnitude: `patch`, `minor`, `major`
- Kind of work: `feature`, `fix`, `removal`, `chore`, `performance`
- Where: `testing`, `tooling`, `doc`
- Severity and state: `critical`, `blocked`, `parked`, `security`
- Discussion: `discussion`

There are no milestones. Work in flight is an open draft pull request, `parked`
marks an issue deliberately set aside until something changes, and every other
open issue is backlog. Themes are epic issues with native sub-issues.


## Versioning

mink follows [semantic versioning](https://semver.org/). A release bump updates
`[project].version` in `mach.toml`, and tags are created on `main` after the
integration merge from `dev`.


## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).

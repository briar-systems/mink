"""the parity lane: mach's link cases linked by mink and judged by their own checks.

each case under <mach>/test/link/cases is a mach project whose case.conf names its
legs, profiles, run mode and checks, and whose expect*.txt is the observable the
current compiler's link records. the lane copies the cases, their shared checks
and mach's std into the run directory, has the compiler emit each case's objects
(`mach build --emit obj`), links them with `mink link` from the case's own target
and link tables, and runs the case's check against mink's image in place of the
compiler's, comparing with the same expect file the compiler's link must match.

every case has one row in test/parity/scope.tsv: in scope, owned by the job that
claims it, or out of scope with the job that owns it and why. a case with no row
or a row with no case fails the lane, so the table covers the cases exactly.
a leg runs natively when it is the host's and under qemu-user otherwise, and a
leg whose emulator is missing is announced as not run.

usage: parity.py --mink <mink> --mach <mach> --mach-src <checkout> --scope <tsv>
                 --work <dir> [--case <name>]...
"""

import argparse
import glob
import os
import platform
import shutil
import subprocess
import sys
import tomllib

# the legs mach runs its link cases on, and what each runs on here
LEGS = ["x86_64-linux", "aarch64-linux", "riscv64-linux", "x86_64-windows", "x86_64-darwin", "aarch64-darwin"]
EMULATORS = {"aarch64": "qemu-aarch64", "riscv64": "qemu-riscv64", "x86_64": "qemu-x86_64"}

# the case's isa, and its os and abi, as mink names its architecture, system, environment
# and format. an abi row of `*` holds for every abi the os has no row of its own for
ARCHES = {"x86_64": "x86_64", "aarch64": "aarch64", "riscv64": "riscv64", "spirv": "spirv"}
SYSTEMS = {
    ("linux", "*"): ("linux", "gnu", "elf"),
    ("freestanding", "spirv"): ("vulkan", None, "spirv"),
    ("freestanding", "*"): ("freestanding", None, "elf"),
    ("windows", "*"): ("windows", "msvc", "coff"),
    ("darwin", "*"): ("darwin", "macos", "macho"),
}

# the kind a format's image is linked as, where it is not an executable
KINDS = {"spirv": "module"}

# the suffix the compiler gives a format's objects, where it is not .o
SUFFIXES = {"spirv": ".spv"}


def system_of(tinfo):
    """the system, environment and format of the case's target"""
    os_ = tinfo["os"]
    return SYSTEMS.get((os_, tinfo.get("abi")), SYSTEMS[(os_, "*")])


def arch_of(isa):
    if isa in ARCHES:
        return ARCHES[isa]
    if isa.startswith("rv32"):
        return "riscv32"
    if isa.startswith("rv64"):
        return "riscv64"
    return None


def host_isa():
    m = platform.machine()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)


def engine(leg):
    """`native`, `qemu:<emulator>`, or None when nothing here runs the leg"""
    isa, _, os_ = leg.partition("-")
    if os_ != "linux" or platform.system() != "Linux":
        return None
    if isa == host_isa():
        return "native"
    q = EMULATORS.get(isa)
    if q and shutil.which(q):
        return "qemu:" + q
    return None


def read_conf(case):
    conf = {"legs": "", "skip": "", "profiles": "debug release", "run": "exec", "target": "",
            "build-flags": "", "self-host": "", "gbuild": "no", "goal": "build"}
    path = os.path.join(case, "case.conf")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            if key not in conf:
                raise SystemExit(f"parity.py: {path}: unknown key '{key}'")
            conf[key] = value.strip()
    return conf


def read_scope(path):
    """the rows keyed by (case, leg), either of which may be `*`. a case's own row
    (case, *) says whether it is in scope, and an out row for (case, leg), for
    (*, leg) or for the case takes the cells it covers out, so no row's place in
    the table decides anything"""
    rows = {}
    for n, line in enumerate(open(path), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 5 or parts[2] not in ("in", "out"):
            raise SystemExit(f"parity.py: {path}:{n}: a row is <case> <leg> <in|out> <owner> <why>")
        key = (parts[0], parts[1])
        if key in rows:
            raise SystemExit(f"parity.py: {path}:{n}: {parts[0]} {parts[1]} has two rows")
        if parts[2] == "in" and (parts[0] == "*" or parts[1] != "*"):
            raise SystemExit(f"parity.py: {path}:{n}: only a case's own row, for every leg, puts it in scope")
        rows[key] = parts[2:]
    return rows


def out_rows(scope, name, leg):
    """the out rows that cover the cell, each as owner and why"""
    return [scope[k][1:] for k in ((name, "*"), ("*", leg), (name, leg)) if k in scope and scope[k][0] == "out"]


def run(argv, cwd, log, env=None):
    with open(log, "w") as f:
        return subprocess.run(argv, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env).returncode


def log_of(tmp):
    return os.path.join(tmp, "link.log")


def first_line(path):
    for line in open(path, errors="replace"):
        if line.strip():
            return line.strip()
    return "no output"


class Lane:
    def __init__(self, args):
        self.a = args
        self.passed = self.failed = self.scoped = self.unrun = 0

    def say(self, word, label, text=""):
        print(f"{word:<13}{label}{': ' + text if text else ''}", flush=True)

    def fail(self, label, text, detail=None):
        self.failed += 1
        self.say("fail", label, text)
        if detail and os.path.exists(detail):
            for line in open(detail, errors="replace").read().splitlines()[:12]:
                print("    " + line)

    def links(self, case, toml, art, target, work):
        """the [link.X] files the artifact names, then those its dependencies export,
        that hold for the target, in order"""
        tinfo = toml["target"][target]
        found = []

        def holds(row):
            return all(("*" in row.get(k, ["*"]) or tinfo.get(k) in row.get(k, ["*"])) for k in ("os", "isa", "abi"))

        def take(name, row):
            if row.get("source") != "local":
                return f"link '{name}' is a {row.get('source')} library, which the lane cannot hand mink"
            found.append(os.path.join(case, row["path"].replace("{project.work}", work)))
            return None

        for name in art.get("link", []):
            row = toml.get("link", {}).get(name)
            if row is None:
                return None, f"the artifact links '{name}', which no [link] table names"
            if holds(row):
                why = take(name, row)
                if why:
                    return None, why
        seen = set()
        pending = [os.path.join(case, d["path"]) for d in toml.get("dep", {}).values() if "path" in d]
        while pending:
            dep = os.path.normpath(pending.pop(0))
            if dep in seen:
                continue
            seen.add(dep)
            dtoml = tomllib.load(open(os.path.join(dep, "mach.toml"), "rb"))
            for name, row in sorted(dtoml.get("link", {}).items()):
                if row.get("export") and holds(row):
                    why = take(name, row)
                    if why:
                        return None, why
            pending += [os.path.join(dep, d["path"]) for d in dtoml.get("dep", {}).values() if "path" in d]
        for f in found:
            if not os.path.exists(f):
                return None, f"the link input {os.path.relpath(f, case)} was not built"
        return found, None

    def link(self, case, label, toml, target, profile, conf, debug, out, tmp, cc):
        """emit the case's objects with the compiler `cc` and link them with mink into
        `out`, None or why it failed"""
        flags = conf["build-flags"].split()
        argv = cc + ["build", ".", "--target", target, "--profile", profile, "--emit", "obj"] + flags
        work = toml["project"]["work"].replace("{target.name}", target).replace("{profile.name}", profile)
        if debug:
            # the -g twin is its own build, in its own work directory
            work = work + "-g"
            argv += ["-d", "-w", work]
        log = os.path.join(tmp, "build-g.log" if debug else "build.log")
        if run(argv, case, log) != 0:
            return f"the compiler emits no objects: {first_line(log)}", log
        objdir = os.path.join(case, work, "obj")
        # the compiler's own objects sit in a directory per module root, and its link
        # takes the dependencies' before the project's, which decides where their
        # data lands
        tinfo = toml["target"][target]
        system, env, fmt = system_of(tinfo)
        own = toml["project"]["id"]
        roots = sorted(d for d in os.listdir(objdir) if os.path.isdir(os.path.join(objdir, d)))
        objects = []
        for r in [d for d in roots if d != own] + [d for d in roots if d == own]:
            objects += sorted(glob.glob(os.path.join(objdir, r, "**", "*" + SUFFIXES.get(fmt, ".o")), recursive=True))
        bins = [a for a in toml["artifact"].values() if a.get("kind") == "bin"]
        if len(bins) != 1:
            return "the case does not build exactly one executable", None
        extra, why = self.links(case, toml, bins[0], target, work)
        if why:
            return why, None
        arch = arch_of(tinfo["isa"])
        kind = KINDS.get(fmt, "static-pie" if "--pie" in flags else "static")
        argv = [self.a.mink, "link"] + objects + extra + ["-o", out, "--kind", kind, "--format", fmt,
                                                          "--arch", arch, "--system", system]
        if env:
            argv += ["--env", env]
        log = os.path.join(tmp, "link-g.log" if debug else "link.log")
        rc = run(argv, case, log)
        with open(os.path.join(tmp, "link.argv"), "a") as f:
            f.write(" ".join(argv) + "\n")
        if rc != 0:
            return f"mink refuses the link: {first_line(log)}", log
        os.chmod(out, 0o755)
        return None, None

    def self_host(self, target, profile):
        """mach's compiler for `target`, its objects emitted by the compiler under
        test and linked by mink, built once per target and profile"""
        key = (target, profile)
        if key not in self.compilers:
            tmp = os.path.join(self.a.work, "cells", f"self-host.{target}.{profile}")
            os.makedirs(tmp, exist_ok=True)
            toml = tomllib.load(open(os.path.join(self.src, "mach.toml"), "rb"))
            conf = {"build-flags": "-a " + toml["project"]["id"]}
            out = os.path.join(tmp, "mach")
            why, _ = self.link(self.src, "self-host", toml, target, profile, conf, False, out, tmp, [self.a.mach])
            self.compilers[key] = (out, why)
        return self.compilers[key]

    def cell(self, case, name, conf, toml, leg, profile, checks):
        label = f"{name} [{leg}/{profile}]"
        target = conf["target"] or leg
        eng = engine(leg)
        tmp = os.path.join(self.a.work, "cells", f"{name}.{leg}.{profile}")
        os.makedirs(tmp, exist_ok=True)
        linkdir = os.path.join(case, "out", "link")
        os.makedirs(linkdir, exist_ok=True)
        prog = os.path.join(linkdir, "prog")
        runner = [] if eng == "native" else [eng.split(":", 1)[1]]
        cc = [self.a.mach]
        if conf["self-host"]:
            # the case is compiled by the compiler cross-built for the leg, linked by mink
            compiler, why = self.self_host(conf["self-host"], profile)
            if why:
                return self.fail(label, "the self-hosted compiler: " + why)
            cc = runner + [compiler]
        why, log = self.link(case, label, toml, target, profile, conf, False, prog, tmp, cc)
        out = os.path.join(tmp, "out.txt")
        if conf["run"] == "build-fails":
            # the compiler's own diagnostic is its own text, so mink's refusal is the observable
            if why is None:
                return self.fail(label, "mink links what the case expects to be refused")
            if not why.startswith("mink refuses the link"):
                return self.fail(label, why, log)
            self.passed += 1
            return self.say("pass", label, "refused: " + why.split(": ", 1)[1])
        if why:
            return self.fail(label, why, log)
        if conf["run"] == "build-warns":
            # the compiler's warning is its own text, so mink's report of the link is the observable
            if os.path.getsize(log_of(tmp)) == 0:
                return self.fail(label, "mink links without a report of what it left out")
            self.passed += 1
            return self.say("pass", label, "reported: " + first_line(log_of(tmp)))
        gprog = ""
        if conf["gbuild"] == "yes":
            gprog = os.path.join(linkdir, "prog-g")
            why, log = self.link(case, label, toml, target, profile, conf, True, gprog, tmp, cc)
            if why:
                return self.fail(label, "the -g twin: " + why, log)
        check = os.path.join(case, "check.sh")
        if not os.path.exists(check):
            check = os.path.join(checks, conf["run"] + ".sh")
        err = os.path.join(tmp, "err.txt")
        if os.path.exists(check):
            with open(out, "w") as o, open(err, "w") as e:
                rc = subprocess.run(["bash", check, eng, leg, prog, gprog, profile], cwd=case, stdout=o, stderr=e).returncode
            if rc != 0:
                return self.fail(label, f"check exit {rc}", err)
        elif conf["run"] == "exec":
            with open(out, "w") as o, open(err, "w") as e:
                rc = subprocess.run(runner + [prog], cwd=case, stdout=o, stderr=e).returncode
            if rc != 0:
                return self.fail(label, f"exit {rc}", err)
        elif conf["run"] == "built":
            if os.path.getsize(prog) == 0:
                return self.fail(label, "the image is empty")
            open(out, "w").write("built=1\n")
        else:
            return self.fail(label, f"no check script for run mode '{conf['run']}'")
        expect = None
        for g in (f"expect.{target}.{profile}.txt", f"expect.{profile}.txt", f"expect.{target}.txt", "expect.txt"):
            if os.path.exists(os.path.join(case, g)):
                expect = os.path.join(case, g)
                break
        if expect is None:
            return self.fail(label, "no expect file", out)
        if open(expect, "rb").read() != open(out, "rb").read():
            diff = os.path.join(tmp, "diff.txt")
            with open(diff, "w") as d:
                subprocess.run(["diff", "-u", expect, out], stdout=d)
            return self.fail(label, f"differs from {os.path.basename(expect)}", diff)
        self.passed += 1
        self.say("pass", label)

    def main(self):
        a = self.a
        src = os.path.join(a.work, "mach")
        shutil.copytree(a.mach_src, src, ignore=shutil.ignore_patterns("out", ".git"))
        self.src = src
        self.compilers = {}
        cases = os.path.join(src, "test", "link", "cases")
        checks = os.path.join(src, "test", "link", "check")
        scope = read_scope(a.scope)
        names = sorted(n for n in os.listdir(cases) if os.path.exists(os.path.join(cases, n, "mach.toml")))
        for n in sorted({k[0] for k in scope} - set(names) - {"*"}):
            self.fail(n, "the scope table names a case mach does not have")
        for name in names:
            if a.case and name not in a.case:
                continue
            if (name, "*") not in scope:
                self.fail(name, "no row in the scope table")
                continue
            if scope[(name, "*")][0] == "out":
                self.scoped += 1
                owner, why = scope[(name, "*")][1:]
                self.say("not in scope", name, f"{owner}, {why}")
                continue
            case = os.path.join(cases, name)
            conf = read_conf(case)
            toml = tomllib.load(open(os.path.join(case, "mach.toml"), "rb"))
            legs = [l for l in (conf["legs"].split() or LEGS) if l not in conf["skip"].split()]
            pulled = os.path.join(a.work, "cells", f"{name}.pull.log")
            os.makedirs(os.path.dirname(pulled), exist_ok=True)
            if run([a.mach, "dep", "pull", "."], case, pulled) != 0:
                self.fail(name, f"mach dep pull: {first_line(pulled)}")
                continue
            for leg in legs:
                if engine(leg) is None:
                    self.unrun += 1
                    self.say("not run", f"{name} [{leg}]", "nothing on this host runs the leg")
                    continue
                outs = out_rows(scope, name, leg)
                if outs:
                    self.scoped += 1
                    self.say("not in scope", f"{name} [{leg}]", "; ".join(f"{o}, {w}" for o, w in outs))
                    continue
                for profile in conf["profiles"].split():
                    self.cell(case, name, conf, toml, leg, profile, checks)
        print(f"{self.passed} pass, {self.failed} fail, {self.scoped} cases or legs not in scope, {self.unrun} legs not run")
        return 1 if self.failed else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mink", required=True)
    p.add_argument("--mach", required=True)
    p.add_argument("--mach-src", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--case", action="append", default=[])
    a = p.parse_args()
    a.mink = os.path.abspath(a.mink)
    a.work = os.path.abspath(a.work)
    if os.sep in a.mach:
        a.mach = os.path.abspath(a.mach)
    sys.exit(Lane(a).main())


if __name__ == "__main__":
    main()

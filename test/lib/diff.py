"""the differential lane: the same objects linked by mink and by the system linkers.

for each program under test/diff/programs (a directory of C files, linked with
test/diff/rt/start.c), each architecture of test/diff/arches.tsv and each of clang
and gcc, the program is compiled with and without -ffunction-sections, linked by
mink (`mink link`) and by every system linker found (lld, and GNU ld where the
column names one on the path), and every image is run natively, under qemu-user or
under qemu-system. mink's image must agree with each system linker's on every field
of test/diff/fields.tsv against the linkers its row names, which fix only what the
specification or the format's convention for the architecture fixes. the line of
a program, architecture and compiler is agree, disagree with the first differing
field, or not run with the reason. a column with no compiler or no runner is not run,
and a link mink refuses as unbuilt (exit 4) is not run with mink's reason.

the named cases of test/diff/cases.tsv link the objects their case.conf builds with
mink and with the platform's linker, and compare one observable: whether the link
is refused (status), or how often a byte string appears in the image (bytes <text>).

the exit status is 1 when any line disagrees.

usage: diff.py --mink <mink> --root <test/diff> --work <dir> [--case <name>]...
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys

CFLAGS = ["-O1", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie", "-fno-stack-protector",
          "-fno-asynchronous-unwind-tables", "-fno-unwind-tables"]
VARIANTS = [("whole", []), ("sections", ["-ffunction-sections", "-fdata-sections"])]
UNBUILT = 4
TIMEOUT = 30


def table(path, width):
    rows = []
    for n, line in enumerate(open(path), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.rstrip("\n").split("\t")
        if len(cells) != width:
            raise SystemExit(f"diff.py: {path}:{n}: a row has {width} cells, this one {len(cells)}")
        rows.append(cells)
    return rows


def found(commands):
    for c in commands.split(","):
        if c != "-" and shutil.which(c):
            return c
    return None


def host_isa():
    m = platform.machine()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)


def run(argv, log, cwd=None, timeout=TIMEOUT):
    with open(log, "w") as f:
        try:
            return subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT, cwd=cwd, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            f.write(f"timed out after {timeout}s\n")
            return None


def first_line(path):
    for line in open(path, errors="replace"):
        if line.strip():
            return line.strip()
    return "no output"


class Arch:
    def __init__(self, row):
        (self.name, self.target, self.gcc, sysenv, self.lld, self.gnu, self.runner, cflags, ldflags,
         self.unrun) = row
        self.system, env = sysenv.split(",")
        self.env = None if env == "-" else env
        self.cflags = [] if cflags == "-" else cflags.split()
        self.ldflags = [] if ldflags == "-" else ldflags.split()

    def compilers(self):
        """each compiler's command for the column, None when the host has none"""
        return {"clang": ["clang", "--target=" + self.target] if shutil.which("clang") else None,
                "gcc": [found(self.gcc)] if found(self.gcc) else None}

    def linkers(self):
        """each system linker's command for the column, or the reason it has none"""
        out = {}
        out["lld"] = (["ld.lld", "-m", self.lld], None) if shutil.which("ld.lld") else (None, "no ld.lld")
        gnu = found(self.gnu)
        out["ld"] = ([gnu], None) if gnu else (None, f"no GNU ld for {self.name} ({self.gnu.replace(',', ' or ')})")
        return out

    def runs(self):
        """the command prefix that runs an image, or the reason nothing does"""
        if self.unrun != "-":
            return None, self.unrun
        kind, _, tool = self.runner.partition(":")
        if kind == "native":
            return ([], None) if host_isa() == self.name and platform.system() == "Linux" else (None, "not the host")
        if not shutil.which(tool):
            return None, f"no {tool}"
        if kind == "qemu-user":
            return [tool], None
        return [tool, "-machine", "virt", "-bios", "none", "-nographic", "-monitor", "none", "-serial", "stdio",
                "-kernel"], None


def fields_of(path):
    out = []
    for name, kind, flags, pattern, key, against in table(path, 6):
        out.append({"name": name, "kind": kind, "flags": flags, "re": re.compile(pattern) if pattern != "-" else None,
                    "key": key, "against": None if against == "*" else set(against.split(","))})
    return out


def readelf(image, flags, cache):
    k = (image, flags)
    if k not in cache:
        r = subprocess.run(["llvm-readelf"] + flags.split() + [image], capture_output=True, text=True)
        cache[k] = r.stdout if r.returncode == 0 else None
    return cache[k]


def entry_symbol(image, cache):
    head = readelf(image, "-hW", cache)
    syms = readelf(image, "-sW", cache)
    if head is None or syms is None:
        return "unreadable"
    m = re.search(r"Entry point address:\s+0x([0-9a-f]+)", head)
    if not m:
        return "none"
    at = int(m.group(1), 16)
    names = sorted(set(re.findall(r"^\s*\d+:\s+0*%x\s+\d+\s+(?:FUNC|NOTYPE)\s+\w+\s+\w+\s+\d+\s+(\S+)$" % at, syms, re.M)))
    return " ".join(names) if names else f"no symbol at the entry"


def observe(field, image, ran, cache):
    if field["kind"] == "run":
        return ran[field["name"]]
    if field["kind"] == "entry":
        return entry_symbol(image, cache)
    text = readelf(image, field["flags"], cache)
    if text is None:
        return "unreadable"
    keys = set()
    for line in text.splitlines():
        m = field["re"].search(line)
        if m:
            keys.add(field["key"].format(**{k: v.strip() for k, v in m.groupdict().items()}))
    return sorted(keys)


class Lane:
    def __init__(self, a):
        self.a = a
        self.disagreed = 0
        self.counts = {"agree": 0, "disagree": 0, "not run": 0}

    def say(self, word, label, text=""):
        self.counts[word] += 1
        if word == "disagree":
            self.disagreed += 1
        print(f"{word:<10}{label}{': ' + text if text else ''}", flush=True)

    def mink_link(self, objects, image, arch, kind, log):
        argv = [self.a.mink, "link"] + objects + ["-o", image, "--kind", kind, "--format", "elf", "--arch",
                                                  arch.name if arch.name != "x86" else "x86", "--system", arch.system]
        if arch.env:
            argv += ["--env", arch.env]
        return run(argv, log)

    def execute(self, runner, image, tmp, tag):
        out = os.path.join(tmp, tag + ".stdout")
        with open(out, "wb") as o:
            try:
                rc = subprocess.run(runner + [image], stdout=o, stderr=subprocess.DEVNULL, timeout=TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        return {"exit": str(rc), "stdout": open(out, "rb").read().decode(errors="replace")}

    def program(self, name, src, arch, fields):
        compilers = arch.compilers()
        linkers = arch.linkers()
        runner, unrun = arch.runs()
        for cc in ("clang", "gcc"):
            label = f"{name} {arch.name} {cc}"
            if compilers[cc] is None:
                self.say("not run", label, f"no {cc} for {arch.name} ({arch.gcc.replace(',', ' or ')})")
                continue
            verdict = self.compare(name, src, arch, cc, compilers[cc], linkers, runner, unrun, fields)
            self.say(verdict[0], label, verdict[1])

    def compare(self, name, src, arch, cc, compiler, linkers, runner, unrun, fields):
        tmp = os.path.join(self.a.work, name, arch.name, cc)
        os.makedirs(tmp, exist_ok=True)
        sources = sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith(".c"))
        sources.append(os.path.join(self.a.root, "rt", "start.c"))
        notes = []
        compared = 0
        for variant, vflags in VARIANTS:
            objects = []
            for s in sources:
                o = os.path.join(tmp, f"{variant}-{os.path.basename(s)}.o")
                log = o + ".log"
                if run(compiler + CFLAGS + vflags + arch.cflags + ["-I", os.path.join(self.a.root, "rt"), "-c", s,
                                                                     "-o", o], log) != 0:
                    return "not run", f"{variant}: {cc} does not compile {os.path.basename(s)}: {first_line(log)}"
                objects.append(o)
            mine = os.path.join(tmp, f"{variant}.mink")
            log = mine + ".log"
            rc = self.mink_link(objects, mine, arch, "static", log)
            if rc == UNBUILT:
                return "not run", f"{variant}: {first_line(log)}"
            if rc != 0:
                return "disagree", f"{variant}: mink refuses the link: {first_line(log)}"
            theirs = []
            for lname, (cmd, why) in linkers.items():
                if cmd is None:
                    notes.append(why)
                    continue
                image = os.path.join(tmp, f"{variant}.{lname}")
                log = image + ".log"
                # mink collects unreferenced sections, so the system linkers are asked to
                if run(cmd + ["-static", "-e", "_start", "--gc-sections"] + arch.ldflags + objects + ["-o", image], log) != 0:
                    return "disagree", f"{variant}: {lname} refuses what mink links: {first_line(log)}"
                theirs.append((lname, image))
            if not theirs:
                return "not run", "no system linker: " + ", ".join(notes)
            cache = {}
            mine_ran = theirs_ran = None
            if runner is not None:
                mine_ran = self.execute(runner, mine, tmp, f"{variant}.mink")
            for lname, image in theirs:
                ran = self.execute(runner, image, tmp, f"{variant}.{lname}") if runner is not None else None
                for f in fields:
                    if f["kind"] == "run" and runner is None:
                        continue
                    if f["against"] is not None and lname not in f["against"]:
                        continue
                    want = observe(f, image, ran, cache)
                    got = observe(f, mine, mine_ran, cache)
                    if want != got:
                        return "disagree", f"{variant}: {f['name']} differs from {lname}: {differs(got, want, lname)}"
                compared += 1
        text = f"{compared} links compared"
        if runner is None:
            text += f", linked only: {unrun}"
            return "not run", text
        if notes:
            text += ", " + ", ".join(sorted(set(notes)))
        return "agree", text

    def case(self, name, settles):
        d = os.path.join(self.a.root, "cases", name)
        conf = {"build": [], "copy": []}
        for line in open(os.path.join(d, "case.conf")):
            if not line.strip() or line.startswith("#"):
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            if k in ("build", "copy"):
                conf[k].append(v.strip())
            else:
                conf[k] = v.strip()
        tmp = os.path.join(self.a.work, "cases", name)
        os.makedirs(tmp, exist_ok=True)
        label = f"case {name} ({settles})"
        for f in conf["copy"]:
            shutil.copy(os.path.join(d, f), tmp)
        for i, cmd in enumerate(conf["build"]):
            argv = cmd.replace("{in}", d).replace("{out}", tmp).split()
            if not shutil.which(argv[0]):
                return self.say("not run", label, f"no {argv[0]}")
            log = os.path.join(tmp, f"build{i}.log")
            if run(argv, log) != 0:
                return self.say("not run", label, f"{argv[0]} does not build the inputs: {first_line(log)}")
        inputs = [os.path.join(tmp, f) for f in conf["inputs"].split()]
        sysargv = conf["system"].split()
        if not shutil.which(sysargv[0]):
            return self.say("not run", label, f"no {sysargv[0]}")
        theirs = os.path.join(tmp, "system.image")
        argv = []
        for t in sysargv:
            if t == "{inputs}":
                argv += inputs
            else:
                argv.append(t.replace("{image}", theirs))
        slog = os.path.join(tmp, "system.log")
        src = run(argv, slog)
        mine = os.path.join(tmp, "mink.image")
        mlog = os.path.join(tmp, "mink.log")
        mrc = run([self.a.mink, "link"] + inputs + ["-o", mine] + conf["mink"].split(), mlog)
        if mrc == UNBUILT:
            return self.say("not run", label, first_line(mlog))
        what = conf["observe"].split(None, 1)
        if what[0] == "status":
            want = "linked" if src == 0 else "refused"
            got = "linked" if mrc == 0 else "refused"
        elif what[0] == "bytes":
            if src != 0:
                return self.say("disagree", label, f"{sysargv[0]} refuses the link: {first_line(slog)}")
            if mrc != 0:
                return self.say("disagree", label, f"mink refuses the link: {first_line(mlog)}")
            needle = what[1].encode()
            want = str(open(theirs, "rb").read().count(needle))
            got = str(open(mine, "rb").read().count(needle))
        else:
            raise SystemExit(f"diff.py: {name}: unknown observable '{what[0]}'")
        if want != got:
            why = f"mink {got}, {sysargv[0]} {want}"
            if got == "refused":
                why += f": {first_line(mlog)}"
            if want == "refused":
                why += f": {first_line(slog)}"
            return self.say("disagree", label, f"{what[0]}: {why}")
        self.say("agree", label, f"{what[0]}: {got}")

    def main(self):
        a = self.a
        arches = [Arch(r) for r in table(os.path.join(a.root, "arches.tsv"), 10)]
        fields = fields_of(os.path.join(a.root, "fields.tsv"))
        programs = os.path.join(a.root, "programs")
        for name in sorted(os.listdir(programs)):
            if a.case and name not in a.case:
                continue
            for arch in arches:
                self.program(name, os.path.join(programs, name), arch, fields)
        for name, settles, _ in table(os.path.join(a.root, "cases.tsv"), 3):
            if a.case and name not in a.case:
                continue
            self.case(name, settles)
        print(", ".join(f"{n} {w}" for w, n in self.counts.items()))
        return 1 if self.disagreed else 0


def differs(got, want, lname):
    """what mink's value has that the system linker's lacks, and the reverse"""
    if not isinstance(got, list):
        return f"mink {got!r}, {lname} {want!r}"
    extra = sorted(set(got) - set(want))
    missing = sorted(set(want) - set(got))
    parts = []
    if extra:
        parts.append("only mink has {" + ", ".join(extra) + "}")
    if missing:
        parts.append(f"only {lname} has {{" + ", ".join(missing) + "}")
    return "; ".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mink", required=True)
    p.add_argument("--root", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--case", action="append", default=[])
    a = p.parse_args()
    a.mink = os.path.abspath(a.mink)
    sys.exit(Lane(a).main())


if __name__ == "__main__":
    main()

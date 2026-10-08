# compare the rule tables of two revisions decision by decision: the dynamic
# decision rows of ELF, PE/COFF, Mach-O and the unbound formats, the layout
# classes of each format and of the layout test, and the long import member
# roles. the old revision's tables may select by first match, the new one's
# must hold for at most one input each. it runs locally and is never part of
# CI.
#
# usage: python3 -I tools/rules/compare.py <old revision> [<new revision>]
#
#   run from the repository root. the new revision defaults to the working
#   tree. tables are read from the Mach sources of each revision.
#
# the dynamic inputs are every reference the dynamic phase can build, by the
# facts its builders hold:
#   a relocation kind has one basis of ABS, MARKER or another, a marker
#   carries nothing but LOADER, and a marker patches no field
#   (reloc.consistent, dynamic.site)
#   WORD and LOW never meet (dynamic.site)
#   a target is exactly one of DEFINED, IMPORTED and UNDEFINED, ABSOLUTE and
#   PREEMPTIBLE are only on a definition, PREEMPTIBLE only where the output
#   is INTERPOSED and the format INTERPOSES, and BOUND exactly for an import,
#   a preemptible definition, or an undefined target in an output that
#   IMPORTS (dynamic.target, dynamic.preemptible)
#   a target names what one symbol kind names: nothing, CODE, DATA,
#   DATA and THREAD, CODE and RESOLVER, or DATA and CELL (model.symbol)
#   an INTERPOSED output IMPORTS (link.kind)
# the class inputs are every set of ALLOC, WRITE, EXEC and TLS flags with
# every set of BITS and RELRO roles. the long member inputs are every set of
# the digits 0 to 9.
#
# one line per table: its name, the inputs compared, how many decide
# differently, and how many the new table holds for more than once. exits 1
# when any does.
import itertools, re, subprocess, sys

def source(rev, path):
    if rev is None:
        return open(path).read()
    return subprocess.run(["git", "show", f"{rev}:{path}"], check=True, capture_output=True, text=True).stdout

def body(text, start):
    # the text between the brace that follows `start` and its match
    i = text.index("{", text.index(start))
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    raise ValueError(start)

def records(text, head):
    # every `head{...}` at the top level of `text`
    out, i = [], 0
    while True:
        i = text.find(head + "{", i)
        if i < 0:
            return out
        j = i + len(head)
        depth = 0
        for k in range(j, len(text)):
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[j + 1:k])
                    i = k + 1
                    break

def fields(rec):
    # the top-level fields of a record literal's body
    out, depth, cur, key = {}, 0, "", None
    for ch in rec + ",":
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            if cur.strip():
                k, v = cur.split(":", 1)
                out[k.strip()] = v.strip()
            cur = ""
        else:
            cur += ch
    return out

def locals_of(text):
    return {m.group(1): m.group(2) for m in re.finditer(r"^\s*(?:pub\s+)?val\s+(\w+)\s*:\s*[\w.]+\s*=\s*([^;{]+);", text, re.M)}

def names(expr, local):
    # the capability names an expression ors together
    out = set()
    for part in expr.split("|"):
        p = part.strip()
        if p in ("0", ""):
            continue
        base = p.split(".")[-1]
        if "." not in p and p in local and not re.fullmatch(r"[0-9][0-9a-fA-Fx_]*", local[p].strip()):
            out |= names(local[p], local)
        else:
            out.add(base)
    return out

def axis(v, local):
    f = fields(v[len("Axis{"):-1]) if v.startswith("Axis{") else {}
    return names(f.get("need", "0"), local), names(f.get("deny", "0"), local)

AXES = ("kind", "site", "target", "output", "format")

def dynamic_rows(text, start):
    local = locals_of(text)
    rows = []
    for r in records(body(text, start), "Row"):
        f = fields(r)
        ax = {a: axis(f[a], local) if a in f else (set(), set()) for a in AXES}
        reason = f.get("reason")
        rows.append((f.get("name", "").strip('"'), ax, f["outcome"].split(".")[-1].lstrip("?"), reason.strip('"') if reason else None))
    return rows, local

def dynamic_caps(text, start, local):
    return names(fields(body(text, start)).get("caps", "0"), local)

NAMED = [set(), {"CODE"}, {"DATA"}, {"DATA", "THREAD"}, {"CODE", "RESOLVER"}, {"DATA", "CELL"}]

def references(interposes):
    kinds = []
    for basis in ("ABS", "MARKER", "PC"):
        for extra in itertools.product([0, 1], repeat=4):
            k = {basis} | {b for b, on in zip(("LOADER", "TLS", "GOT", "PLT"), extra) if on}
            if basis == "MARKER" and k & {"TLS", "GOT", "PLT"}:
                continue
            kinds.append(k)
    sites = [s for s in (set(c) for n in range(4) for c in itertools.combinations(("WORD", "WRITABLE", "LOW"), n)) if not {"WORD", "LOW"} <= s]
    outs = [o for o in (set(c) for n in range(4) for c in itertools.combinations(("IMPORTS", "PIC", "INTERPOSED"), n)) if "INTERPOSED" not in o or "IMPORTS" in o]
    for k in kinds:
        for s in sites:
            if "MARKER" in k and s:
                continue
            for o in outs:
                for origin in ("DEFINED", "IMPORTED", "UNDEFINED"):
                    for pre, fixed in itertools.product([0, 1], repeat=2):
                        if origin != "DEFINED" and (pre or fixed):
                            continue
                        if pre and not ("INTERPOSED" in o and interposes):
                            continue
                        bound = origin == "IMPORTED" or pre or (origin == "UNDEFINED" and "IMPORTS" in o)
                        for named in NAMED:
                            t = {origin} | named
                            if pre:
                                t.add("PREEMPTIBLE")
                            if fixed:
                                t.add("ABSOLUTE")
                            if bound:
                                t.add("BOUND")
                            yield {"kind": k, "site": s, "target": t, "output": o}

def holds(ax, caps):
    need, deny = ax
    return need <= caps and not (deny & caps)

def row_holds(row, ref, fmt):
    ax = row[1]
    return all(holds(ax[a], ref[a]) for a in AXES[:4]) and holds(ax["format"], fmt)

DYNAMIC = [
    ("elf", "src/lib/elf/rules.mach", "DYNAMIC_ROWS:", "pub val DYNAMIC: dynamic.Rules"),
    ("coff", "src/lib/coff/rules.mach", "DYNAMIC_ROWS:", "pub val DYNAMIC: dynamic.Rules"),
    ("macho", "src/lib/macho/rules.mach", "DYNAMIC_ROWS:", "pub val DYNAMIC: dynamic.Rules"),
    ("unbound", "src/lib/link/dynamic.mach", "UNBOUND_ROWS:", "pub val UNBOUND: Rules"),
]

def compare_dynamic(old_rev, new_rev):
    bad = 0
    for name, path, rows_at, rules_at in DYNAMIC:
        old_text, new_text = source(old_rev, path), source(new_rev, path)
        old, old_local = dynamic_rows(old_text, rows_at)
        new, new_local = dynamic_rows(new_text, rows_at)
        old_fmt = dynamic_caps(old_text, rules_at, old_local)
        new_fmt = dynamic_caps(new_text, rules_at, new_local)
        n = differ = multi = 0
        for ref in references("INTERPOSES" in new_fmt):
            n += 1
            want = next(((r[2], r[3]) for r in old if row_holds(r, ref, old_fmt)), None)
            got = [(r[2], r[3]) for r in new if row_holds(r, ref, new_fmt)]
            if len(got) > 1:
                multi += 1
            elif (got[0] if got else None) != want:
                differ += 1
        print(f"dynamic {name}: {len(old)} rows to {len(new)}, {n} references, {differ} mismatches, {multi} held more than once")
        bad += differ + multi
    return bad

CLASSES = [
    ("elf", "src/lib/elf/rules.mach", "CLASSES:"),
    ("coff", "src/lib/coff/rules.mach", "CLASSES:"),
    ("macho", "src/lib/macho/rules.mach", "CLASSES:"),
    ("layout test", "src/lib/link/layout.mach", "TEST_CLASSES:"),
]

def classes(text, start):
    local = locals_of(text)
    out = []
    for pos, r in enumerate(records(body(text, start), "Class")):
        f = fields(r)
        m = re.search(r"\?(\w+)", f["load"])
        load = m.group(1) if m else None
        if "flag_mask" in f:
            # a value under a mask, its order its rank
            fv, fm = names(f.get("flags", "0"), local), names(f.get("flag_mask", "0"), local)
            rv, rm = names(f.get("roles", "0"), local), names(f.get("role_mask", "0"), local)
            out.append(((fv, fm - fv), (rv, rm - rv), pos, load))
        else:
            fa = axis(f["flags"], local) if "flags" in f else (set(), set())
            ra = axis(f["roles"], local) if "roles" in f else (set(), set())
            out.append((fa, ra, int(f["rank"]), load))
    return out

def compare_classes(old_rev, new_rev):
    bad = 0
    sets = [set(c) for n in range(5) for c in itertools.combinations(("ALLOC", "WRITE", "EXEC", "TLS"), n)]
    roles = [set(c) for n in range(3) for c in itertools.combinations(("BITS", "RELRO"), n)]
    for name, path, start in CLASSES:
        old, new = classes(source(old_rev, path), start), classes(source(new_rev, path), start)
        n = differ = multi = 0
        for fl in sets:
            for ro in roles:
                n += 1
                want = next(((c[2], c[3]) for c in old if holds(c[0], fl) and holds(c[1], ro)), None)
                got = [(c[2], c[3]) for c in new if holds(c[0], fl) and holds(c[1], ro)]
                if len(got) > 1:
                    multi += 1
                elif (got[0] if got else None) != want:
                    differ += 1
        print(f"classes {name}: {len(old)} classes to {len(new)}, {n} sections, {differ} mismatches, {multi} held more than once")
        bad += differ + multi
    return bad

def digits_of(rev):
    text = source(rev, "src/lib/coff/tables.mach")
    return {m.group(1): int(m.group(2), 0) for m in re.finditer(r"pub val (IDATA_\w+):\s*Constant\s*=\s*Constant\{[^}]*value:\s*(\w+)", text)}

def constants(expr, digits):
    return {digits[m] for m in re.findall(r"tables\.(IDATA_\w+)", expr)}

def long_roles(rev):
    text = source(rev, "src/lib/coff/import.mach")
    digits = digits_of(rev)
    roles = [fields(r) for r in records(body(text, "LONG_ROLES:"), "LongRole")]
    names_ = [r["name"].strip('"') for r in roles]
    if "LONG_FORMS:" not in text:
        # the first role whose sections the member holds
        return [(constants(r.get("first", "") + r.get("second", ""), digits), set(), names_[i]) for i, r in enumerate(roles)]
    out = []
    for r in records(body(text, "LONG_FORMS:"), "LongForm"):
        f = fields(r)
        role = int(re.search(r"LONG_ROLES\[(\d+)\]", f["role"]).group(1))
        out.append((constants(f.get("need", ""), digits), constants(f.get("deny", ""), digits), names_[role]))
    return out

def compare_long(old_rev, new_rev):
    old, new = long_roles(old_rev), long_roles(new_rev)
    n = differ = multi = 0
    for bits in range(1 << 10):
        held = {d for d in range(10) if bits >> d & 1}
        n += 1
        want = next((r[2] for r in old if r[0] <= held and not (r[1] & held)), None)
        got = [r[2] for r in new if r[0] <= held and not (r[1] & held)]
        if len(got) > 1:
            multi += 1
        elif (got[0] if got else None) != want:
            differ += 1
    print(f"long import roles: {len(old)} rows to {len(new)}, {n} section sets, {differ} mismatches, {multi} held more than once")
    return differ + multi

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(__doc__ or "usage: python3 -I tools/rules/compare.py <old revision> [<new revision>]", file=sys.stderr)
        sys.exit(2)
    old_rev = sys.argv[1]
    new_rev = sys.argv[2] if len(sys.argv) == 3 else None
    bad = compare_dynamic(old_rev, new_rev) + compare_classes(old_rev, new_rev) + compare_long(old_rev, new_rev)
    sys.exit(1 if bad else 0)

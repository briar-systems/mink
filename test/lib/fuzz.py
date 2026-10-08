"""the hostile input driver: mutate seeds and read each mutant in a child process.

a refusal (exit 1) and a completed read (exit 0) pass. a signal, a timeout, an
exit code of 2 or more, or a read past the end of the input (the child places the
input against an unmapped page, so it dies of a signal) is a finding. the input
that caused it is saved under the output directory and reported with its path
and hash. the driver knows no format: it takes the readers and the claim of each
file from the child, and mutates bytes.
"""
import argparse
import concurrent.futures
import hashlib
import os
import random
import resource
import signal
import subprocess
import sys
import threading
import time

MAX_SEED = 256 * 1024
INTERESTING = (0x00, 0x01, 0x7F, 0x80, 0xFF)
WIDTHS = (1, 2, 4, 8)


def run(argv, **kw):
    return subprocess.run(argv, capture_output=True, **kw)


def limits(mem):
    def apply():
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def readers(fuzz):
    out = run([fuzz, "readers"], check=True).stdout.decode()
    return out.split()


def gather(fuzz, dirs, names):
    seeds = {n: [] for n in names}
    for d in dirs:
        for root, _, files in os.walk(d):
            for f in sorted(files):
                p = os.path.join(root, f)
                if os.path.islink(p) or os.path.getsize(p) > MAX_SEED:
                    continue
                r = run([fuzz, "sniff", p])
                name = r.stdout.decode().strip()
                if r.returncode == 0 and name in seeds:
                    seeds[name].append(p)
                elif r.returncode == 1:
                    continue
                elif r.returncode != 0:
                    print("fuzz: sniffing %s failed (%d)" % (p, r.returncode), file=sys.stderr)
    return seeds


def put(b, at, width, value, big):
    b[at:at + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, "big" if big else "little")


def mutate(rng, data):
    b = bytearray(data)
    for _ in range(rng.choice((1, 1, 2, 3, 5))):
        n = len(b)
        op = rng.randrange(8)
        if n == 0:
            b = bytearray(rng.randbytes(rng.randrange(1, 64)))
        elif op == 0:
            b[rng.randrange(n)] ^= 1 << rng.randrange(8)
        elif op == 1:
            b[rng.randrange(n)] = rng.choice(INTERESTING)
        elif op == 2:
            del b[rng.randrange(n):]
        elif op == 3:
            w = rng.choice(WIDTHS)
            if n >= w:
                v = rng.choice((0xFF, 0x7F, 0x80, 0x100, 0xFFFF, 0x7FFFFFFF, 0xFFFFFFFF, 2**63, 2**64 - 1,
                                n, n + 1, n * 2, rng.getrandbits(8 * w)))
                put(b, rng.randrange(n - w + 1), w, v, rng.random() < 0.2)
        elif op == 4:
            s = rng.randrange(n)
            c = b[s:s + rng.randrange(1, 128)]
            at = rng.randrange(n + 1)
            b[at:at] = c
        elif op == 5:
            k = rng.randrange(1, min(n, 128) + 1)
            x, y = rng.randrange(n - k + 1), rng.randrange(n - k + 1)
            a, c = bytes(b[x:x + k]), bytes(b[y:y + k])
            b[x:x + k], b[y:y + k] = c, a
        elif op == 6:
            k = rng.randrange(1, min(n, 64) + 1)
            x = rng.randrange(n - k + 1)
            b[x:x + k] = bytes(k)
        else:
            k = rng.randrange(1, 64)
            b.extend(rng.randbytes(k))
    return bytes(b)


def probe(fuzz, reader, path, timeout, mem):
    try:
        r = subprocess.run([fuzz, "read", reader, path], capture_output=True, timeout=timeout,
                           preexec_fn=limits(mem))
    except subprocess.TimeoutExpired:
        return "hang (over %ds)" % timeout
    if r.returncode in (0, 1):
        return None
    if r.returncode < 0:
        return "signal %s" % signal.Signals(-r.returncode).name
    return "exit %d: %s" % (r.returncode, r.stderr.decode(errors="replace").strip()[:200])


def one(args, reader, scratch, data):
    h = hashlib.sha256(data).hexdigest()
    path = os.path.join(scratch, "%s.%d.bin" % (h, threading.get_ident()))
    with open(path, "wb") as f:
        f.write(data)
    why = probe(args.fuzz, reader, path, args.timeout, args.mem)
    if why is None:
        os.unlink(path)
        return None
    kept = os.path.join(args.out, reader)
    os.makedirs(kept, exist_ok=True)
    final = os.path.join(kept, h + ".bin")
    os.replace(path, final)
    return (why, final, h)


def lane(args, reader, seeds):
    scratch = os.path.join(args.out, ".scratch-%s" % reader)
    os.makedirs(scratch, exist_ok=True)
    data = [open(p, "rb").read() for p in seeds]
    found = {}
    count = 0
    deadline = time.monotonic() + args.time
    rng = random.Random(args.rng)
    pending = list(data)

    def batch():
        out = []
        for _ in range(args.jobs * 4):
            out.append(pending.pop() if pending else mutate(rng, rng.choice(data)))
        return out

    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        while time.monotonic() < deadline:
            if not data:
                break
            work = [(i, pool.submit(one, args, reader, scratch, b)) for i, b in enumerate(batch())]
            for _, fut in work:
                count += 1
                res = fut.result()
                if res and res[2] not in found:
                    found[res[2]] = res
    os.rmdir(scratch)
    return count, list(found.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuzz", required=True)
    ap.add_argument("--time", type=int, required=True, help="seconds per reader")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rng", type=int, default=None)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=5)
    ap.add_argument("--mem", type=int, default=2 << 30)
    ap.add_argument("seeds", nargs="+")
    args = ap.parse_args()
    if args.rng is None:
        args.rng = random.SystemRandom().randrange(2**32)
    print("rng seed %d" % args.rng)
    names = readers(args.fuzz)
    seeds = gather(args.fuzz, args.seeds, names)
    bad = 0
    for name in names:
        if not seeds[name]:
            print("%s: no seeds" % name)
            continue
        count, found = lane(args, name, seeds[name])
        print("%s: %d seeds, %d inputs, %d findings" % (name, len(seeds[name]), count, len(found)))
        for why, path, h in found:
            print("  %s: %s sha256 %s" % (why, path, h))
        bad += len(found)
    return 1 if bad else 0


sys.exit(main())

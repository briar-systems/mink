#!/usr/bin/env python3
"""mutate PE images and dump each mutant, counting the outcomes of mink dump.

usage: python3 -I tools/coff/mutate-dump.py <mink> <run> <count> <seed> <image>...

<run> names a fresh directory, which holds the mutants and the report. each mutant
flips bytes of one image at offsets chosen by the seed, from the headers and from
the whole file, and is written as <run>/<n>.bin. `mink dump` runs on each, and the
report counts how many dumped, how many were refused and the refusal texts. a refusal
text names the stage that refused: a read refusal comes from the reader, and any other
text comes from the dump. nothing here runs in CI.
"""
import os
import random
import subprocess
import sys


def main():
    if len(sys.argv) < 6:
        sys.exit("usage: python3 -I tools/coff/mutate-dump.py <mink> <run> <count> <seed> <image>...")
    mink, run, count, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    images = sys.argv[5:]
    if os.path.exists(run):
        sys.exit("mutate-dump: %s exists, name a fresh directory" % run)
    os.makedirs(run)
    rng = random.Random(seed)
    texts = {}
    dumped = 0
    for n in range(count):
        src = images[rng.randrange(len(images))]
        data = bytearray(open(src, "rb").read())
        flips = rng.randrange(1, 9)
        for _ in range(flips):
            if rng.random() < 0.5:
                at = rng.randrange(0, min(len(data), 0x400))
            else:
                at = rng.randrange(0, len(data))
            data[at] = rng.randrange(256)
        path = os.path.join(run, "%d.bin" % n)
        with open(path, "wb") as f:
            f.write(data)
        proc = subprocess.run([mink, "dump", path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if proc.returncode == 0:
            dumped += 1
            continue
        text = proc.stderr.decode("utf-8", "replace").strip().split("\n")[0]
        texts[text] = texts.get(text, 0) + 1
    report = os.path.join(run, "report.txt")
    with open(report, "w") as f:
        f.write("mutants %d, dumped %d, refused %d\n" % (count, dumped, count - dumped))
        for text, k in sorted(texts.items(), key=lambda kv: -kv[1]):
            f.write("%6d  %s\n" % (k, text))
    print(open(report).read())


if __name__ == "__main__":
    main()

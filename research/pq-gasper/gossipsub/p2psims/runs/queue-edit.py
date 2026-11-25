#!/usr/bin/env python3
"""Edit runs/queue-night.txt atomically (temp file + rename), so night.sh never reads a half-written queue.

usage: python3 runs/queue-edit.py QUEUE NAME NOTE [NEW_LINE]
    Turns NAME's active line into '# NOTE: <old line>' and puts NEW_LINE (if given) after it.
usage: python3 runs/queue-edit.py QUEUE NAME NOTE --scale-down
    Same, then puts NAME's line back one step down the peer-scale ladder 1.0 > 0.75 > 0.5 > 0.25 (name tag -psNNN
    changed to match), and moves every later active line with the same host count and peer scale down the same step.
    Prints the replacement line on stdout and each moved line on stderr. Exits 2 when NAME is already at the bottom of
    the ladder (its line is only commented out).
Exits 1 if NAME has no active line."""
import os
import re
import sys

LADDER = [1.0, 0.75, 0.5, 0.25]
REAL_SCALE = 0.25  # runs/night.sh's REAL flags carry --peer-scale 0.25; a later --peer-scale on the line wins


def scale_of(f):
    s = REAL_SCALE
    for i in range(len(f) - 1):
        if f[i] == "--peer-scale":
            s = float(f[i + 1])
    return s


def rescale(f, new, taken):
    """Queue line fields `f` at peer scale `new`: every --peer-scale value replaced and the name's -psNNN tag set."""
    tag = f"-ps{round(new * 100):03d}"
    name = re.sub(r"-ps\d{3}", tag, f[0]) if re.search(r"-ps\d{3}", f[0]) else f[0] + tag
    base, k = name, 2
    while name in taken:
        name, k = f"{base}-r{k}", k + 1
    taken.add(name)
    rest = [f"{new:g}" if i > 0 and f[i - 1] == "--peer-scale" else x for i, x in enumerate(f) if i > 0]
    if "--peer-scale" not in f:
        rest += ["--peer-scale", f"{new:g}"]
    return [name] + rest


def main():
    path, name, note = sys.argv[1:4]
    extra = sys.argv[4].strip() if len(sys.argv) > 4 else ""
    down = extra == "--scale-down"
    lines = open(path).readlines()
    idx = next((i for i, l in enumerate(lines) if l.split() and l.split()[0] == name), None)
    if idx is None:
        sys.exit(f"queue-edit: no active line for {name} in {path}")
    runs = os.path.dirname(os.path.abspath(path))
    taken = {l.split()[0] for l in lines if l.split() and not l.startswith("#")} | set(os.listdir(runs))
    f = lines[idx].split()
    out = lines[:idx] + [f"# {note}: {lines[idx].strip()}\n"]
    status = 0
    if down:
        old = scale_of(f)
        lower = [s for s in LADDER if s < old - 1e-9]
        if lower:
            new = lower[0]
            taken.discard(name)
            g = rescale(f, new, taken)
            out.append(" ".join(g) + "\n")
            print(" ".join(g))
            for l in lines[idx + 1:]:
                h = l.split()
                if h and not l.startswith("#") and h[1] == f[1] and abs(scale_of(h) - old) < 1e-9:
                    taken.discard(h[0])
                    k = rescale(h, new, taken)
                    print(f"queue-edit: {h[0]} -> {k[0]} (peer scale x{old:g} -> x{new:g})", file=sys.stderr)
                    out.append(" ".join(k) + "\n")
                else:
                    out.append(l)
        else:
            out += lines[idx + 1:]
            status = 2
    else:
        if extra:
            out.append(extra + "\n")
        out += lines[idx + 1:]
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.writelines(out)
    os.replace(tmp, path)
    sys.exit(status)


if __name__ == "__main__":
    main()

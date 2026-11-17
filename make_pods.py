#!/usr/bin/env python3
"""Create pod folders and copy router config templates into them.

Numbering (see numbering.txt):
  - everything counts from 1, single digits padded to two characters
  - leaf router:  le[pod][leaf]   leaf numbers 1-16   -> le0101 .. le0116
  - spine router: sp[pod][spine]  spine numbers 33-48 -> sp0133 .. sp0148

Output layout matches the bind paths in templates/pod/pod-template.yaml
(pods/podtt/lettqq.conf):

  pods/pod01/le0101.conf ... pods/pod01/sp0148.conf   (32 files per pod)

Placeholders in the templates are filled in on description and address
lines only (everything else, e.g. hostname, is copied as-is):
  tt  pod number
  qq  this router's number (leaf 01-16, spine 33-48)
  pp  plane number the spine uplinks to (spines 33-36 -> 01, 37-40 -> 02,
      41-44 -> 03, 45-48 -> 04; matches templates/pod/pod-template.yaml)

Identifiers and IPv6 groups use the padded form (1 -> 01). IPv4 octets are
left unpadded (10.10.1.1, not 10.10.01.01): a leading zero is read as octal
by some tools and rejected by others.
"""

import argparse
import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE / "templates" / "pod"
LEAF_TEMPLATE = TEMPLATE_DIR / "leaf-template.conf"
SPINE_TEMPLATE = TEMPLATE_DIR / "spine-template.conf"

POD_COUNT = 4
LEAF_NUMBERS = range(1, 17)    # 1-16
SPINE_NUMBERS = range(33, 49)  # 33-48
SPINES_PER_PLANE = 4           # 33-36 -> plane 1, 37-40 -> plane 2, ...

PLACEHOLDER = re.compile(r"tt|qq|pp")
IPV4_ADDRESS = re.compile(r"^\s*ip address ")
FILLED_LINE = re.compile(r"^\s*(description|ip address|ipv6 address) ")


def pad(n: int) -> str:
    """Pad a number to two characters (1 -> '01')."""
    return f"{n:02d}"


def router_id(role: str, pod: int, number: int) -> str:
    """Router identifier, e.g. router_id('le', 1, 3) -> 'le0103'."""
    return f"{role}{pad(pod)}{pad(number)}"


def plane_for_spine(spine: int) -> int:
    """Plane a spine uplinks to: 33-36 -> 1, 37-40 -> 2, 41-44 -> 3, 45-48 -> 4."""
    return (spine - SPINE_NUMBERS.start) // SPINES_PER_PLANE + 1


def fill_line(line: str, values: dict) -> str:
    """Replace tt/qq/pp on one line; IPv4 addresses get unpadded numbers."""
    padded = not IPV4_ADDRESS.match(line)
    return PLACEHOLDER.sub(
        lambda m: pad(values[m.group()]) if padded else str(values[m.group()]),
        line)


def render(template: Path, pod: int, number: int, plane: int = 0) -> str:
    """Fill in the placeholders on description and address lines."""
    values = {"tt": pod, "qq": number, "pp": plane}
    out = []
    for line in template.read_text().splitlines(keepends=True):
        if FILLED_LINE.match(line):
            if "pp" in line and not plane:
                raise ValueError(f"{template.name}: 'pp' needs a plane number: {line.strip()}")
            line = fill_line(line, values)
        out.append(line)
    return "".join(out)


def build_pod(out_dir: Path, pod: int) -> Path:
    pod_dir = out_dir / f"pod{pad(pod)}"
    pod_dir.mkdir(parents=True, exist_ok=True)

    for leaf in LEAF_NUMBERS:
        (pod_dir / f"{router_id('le', pod, leaf)}.conf").write_text(
            render(LEAF_TEMPLATE, pod, leaf))
    for spine in SPINE_NUMBERS:
        (pod_dir / f"{router_id('sp', pod, spine)}.conf").write_text(
            render(SPINE_TEMPLATE, pod, spine, plane_for_spine(spine)))

    return pod_dir


def clean(out_dir: Path) -> None:
    """Delete pod folders left by a previous run.

    Only podNN directories inside out_dir are removed, so pointing --out at
    an existing directory can't wipe anything this script didn't create.
    """
    if not out_dir.is_dir():
        return
    for old in sorted(out_dir.glob("pod[0-9][0-9]")):
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)
            print(f"removed {old}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, default=BASE / "pods",
                        help="output directory (default: ./pods next to this script)")
    parser.add_argument("-n", "--pods", type=int, default=POD_COUNT,
                        help=f"number of pods (default: {POD_COUNT})")
    args = parser.parse_args()

    clean(args.out)
    for pod in range(1, args.pods + 1):
        pod_dir = build_pod(args.out, pod)
        count = len(list(pod_dir.glob("*.conf")))
        print(f"{pod_dir}: {count} files")


if __name__ == "__main__":
    main()

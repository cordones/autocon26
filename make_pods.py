#!/usr/bin/env python3
"""Create pod and plane folders and fill router config templates into them.

Numbering (see numbering.txt):
  - everything counts from 1, single digits padded to two characters
  - leaf router:  le[pod][leaf]   leaf numbers 1-16   -> le0101 .. le0116
  - spine router: sp[pod][spine]  spine numbers 33-48 -> sp0133 .. sp0148
  - plane router: fa[plane][rtr]  router numbers 1-16  -> fa0101 .. fa0116

Pod output matches the bind paths in templates/pod/pod-template.yaml
(pods/podtt/lettqq.conf); plane output mirrors it:

  pods/pod01/le0101.conf ... pods/pod01/sp0148.conf       (32 files per pod)
  planes/plane01/fa0101.conf ... planes/plane01/fa0116.conf (16 per plane)

Placeholders in the templates are filled in on hostname, description, address
and IS-IS net lines only (everything else is copied as-is):
  pod templates
    tt  pod number
    qq  this router's number (leaf 01-16, spine 33-48)
    pp  plane number the spine uplinks to (spines 33-36 -> 01, 37-40 -> 02,
        41-44 -> 03, 45-48 -> 04; matches templates/pod/pod-template.yaml)
  plane template
    tt     plane number
    qq     this router's number (01-16)
    s1-s4  the plane's four spine numbers (plane 1: 33-36, plane 2: 37-40, ...)
    Pod numbers are literal in the template (pod 01 on eth01-04 ...
    pod 04 on eth13-16), so it covers exactly 4 pods.

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
PLANE_TEMPLATE = BASE / "templates" / "plane" / "plane-template.conf"

POD_COUNT = 4
PLANE_TEMPLATE_PODS = 4        # pods written into the plane template's ports
LEAF_NUMBERS = range(1, 17)    # 1-16
SPINE_NUMBERS = range(33, 49)  # 33-48
SPINES_PER_PLANE = 4           # 33-36 -> plane 1, 37-40 -> plane 2, ...
PLANE_COUNT = len(SPINE_NUMBERS) // SPINES_PER_PLANE
PLANE_ROUTER_NUMBERS = range(1, 17)  # 1-16

PLACEHOLDER = re.compile(r"tt|qq|pp|s[1-4]")
IPV4_ADDRESS = re.compile(r"^\s*ip address ")
FILLED_LINE = re.compile(r"^\s*(hostname|description|ip address|ipv6 address|net) ")


def pad(n: int) -> str:
    """Pad a number to two characters (1 -> '01')."""
    return f"{n:02d}"


def router_id(role: str, pod: int, number: int) -> str:
    """Router identifier, e.g. router_id('le', 1, 3) -> 'le0103'."""
    return f"{role}{pad(pod)}{pad(number)}"


def plane_for_spine(spine: int) -> int:
    """Plane a spine uplinks to: 33-36 -> 1, 37-40 -> 2, 41-44 -> 3, 45-48 -> 4."""
    return (spine - SPINE_NUMBERS.start) // SPINES_PER_PLANE + 1


def spines_for_plane(plane: int) -> list:
    """The four spine numbers on a plane: 1 -> [33..36], 2 -> [37..40], ..."""
    first = SPINE_NUMBERS.start + (plane - 1) * SPINES_PER_PLANE
    return list(range(first, first + SPINES_PER_PLANE))


def fill_line(line: str, values: dict, template: Path) -> str:
    """Replace placeholders on one line; IPv4 addresses get unpadded numbers."""
    padded = not IPV4_ADDRESS.match(line)

    def value(m):
        token = m.group()
        if token not in values:
            raise ValueError(f"{template.name}: no value for '{token}': {line.strip()}")
        return pad(values[token]) if padded else str(values[token])

    return PLACEHOLDER.sub(value, line)


def render(template: Path, values: dict) -> str:
    """Fill in the placeholders on description and address lines."""
    out = []
    for line in template.read_text().splitlines(keepends=True):
        if FILLED_LINE.match(line):
            line = fill_line(line, values, template)
        out.append(line)
    return "".join(out)


def build_pod(out_dir: Path, pod: int) -> Path:
    pod_dir = out_dir / f"pod{pad(pod)}"
    pod_dir.mkdir(parents=True, exist_ok=True)

    for leaf in LEAF_NUMBERS:
        (pod_dir / f"{router_id('le', pod, leaf)}.conf").write_text(
            render(LEAF_TEMPLATE, {"tt": pod, "qq": leaf}))
    for spine in SPINE_NUMBERS:
        (pod_dir / f"{router_id('sp', pod, spine)}.conf").write_text(
            render(SPINE_TEMPLATE, {"tt": pod, "qq": spine, "pp": plane_for_spine(spine)}))

    return pod_dir


def build_plane(out_dir: Path, plane: int) -> Path:
    plane_dir = out_dir / f"plane{pad(plane)}"
    plane_dir.mkdir(parents=True, exist_ok=True)

    spines = {f"s{k}": n for k, n in enumerate(spines_for_plane(plane), start=1)}
    for rtr in PLANE_ROUTER_NUMBERS:
        (plane_dir / f"{router_id('fa', plane, rtr)}.conf").write_text(
            render(PLANE_TEMPLATE, {"tt": plane, "qq": rtr, **spines}))

    return plane_dir


def clean(out_dir: Path, prefix: str) -> None:
    """Delete <prefix>NN folders left by a previous run.

    Only <prefix>NN directories inside out_dir are removed, so pointing an
    output option at an existing directory can't wipe anything this script
    didn't create.
    """
    if not out_dir.is_dir():
        return
    for old in sorted(out_dir.glob(f"{prefix}[0-9][0-9]")):
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)
            print(f"removed {old}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, default=BASE / "pods",
                        help="pod output directory (default: ./pods next to this script)")
    parser.add_argument("-p", "--planes-out", type=Path, default=BASE / "planes",
                        help="plane output directory (default: ./planes next to this script)")
    parser.add_argument("-n", "--pods", type=int, default=POD_COUNT,
                        help=f"number of pods (default: {POD_COUNT})")
    args = parser.parse_args()

    if args.pods != PLANE_TEMPLATE_PODS:
        print(f"warning: the plane template has ports for {PLANE_TEMPLATE_PODS} pods; "
              f"plane configs won't match a {args.pods}-pod build")

    clean(args.out, "pod")
    for pod in range(1, args.pods + 1):
        pod_dir = build_pod(args.out, pod)
        count = len(list(pod_dir.glob("*.conf")))
        print(f"{pod_dir}: {count} files")

    clean(args.planes_out, "plane")
    for plane in range(1, PLANE_COUNT + 1):
        plane_dir = build_plane(args.planes_out, plane)
        count = len(list(plane_dir.glob("*.conf")))
        print(f"{plane_dir}: {count} files")


if __name__ == "__main__":
    main()

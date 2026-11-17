#!/usr/bin/env python3
"""Create pod folders and copy router config templates into them.

Numbering (see numbering.txt):
  - everything counts from 1, single digits padded to two characters
  - leaf router:  le[pod][leaf]   leaf numbers 1-16   -> le0101 .. le0116
  - spine router: sp[pod][spine]  spine numbers 33-48 -> sp0133 .. sp0148

Output layout matches the bind paths in templates/pod/pod-template.yaml
(pods/podtt/lettqq.conf):

  pods/pod01/le0101.conf ... pods/pod01/sp0148.conf   (32 files per pod)

The files are straight copies of the templates; the tt/qq placeholders are
not filled in here.
"""

import argparse
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE / "templates" / "pod"
LEAF_TEMPLATE = TEMPLATE_DIR / "leaf-template.conf"
SPINE_TEMPLATE = TEMPLATE_DIR / "spine-template.conf"

POD_COUNT = 4
LEAF_NUMBERS = range(1, 17)    # 1-16
SPINE_NUMBERS = range(33, 49)  # 33-48


def pad(n: int) -> str:
    """Pad a number to two characters (1 -> '01')."""
    return f"{n:02d}"


def router_id(role: str, pod: int, number: int) -> str:
    """Router identifier, e.g. router_id('le', 1, 3) -> 'le0103'."""
    return f"{role}{pad(pod)}{pad(number)}"


def build_pod(out_dir: Path, pod: int) -> Path:
    pod_dir = out_dir / f"pod{pad(pod)}"
    pod_dir.mkdir(parents=True, exist_ok=True)

    for leaf in LEAF_NUMBERS:
        shutil.copyfile(LEAF_TEMPLATE, pod_dir / f"{router_id('le', pod, leaf)}.conf")
    for spine in SPINE_NUMBERS:
        shutil.copyfile(SPINE_TEMPLATE, pod_dir / f"{router_id('sp', pod, spine)}.conf")

    return pod_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, default=BASE / "pods",
                        help="output directory (default: ./pods next to this script)")
    parser.add_argument("-n", "--pods", type=int, default=POD_COUNT,
                        help=f"number of pods (default: {POD_COUNT})")
    args = parser.parse_args()

    for pod in range(1, args.pods + 1):
        pod_dir = build_pod(args.out, pod)
        count = len(list(pod_dir.glob("*.conf")))
        print(f"{pod_dir}: {count} files")


if __name__ == "__main__":
    main()

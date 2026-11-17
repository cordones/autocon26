#!/usr/bin/env python3
"""Build the containerlab topology file for the four pods and four planes.

Writes lab/fabric.clab.yml (next to this script). The file lives one folder
below the repo, so every bind path starts with ../ :

  groups   ../daemons.txt, ../vtysh.conf
  pods     ../pods/podNN/leNNRR.conf, ../pods/podNN/spNNRR.conf
  planes   ../planes/planeNN/faNNRR.conf

Pod nodes and all links come from templates/pod/pod-template.yaml, filled in
once per pod:
  tt     pod number                               (lett01 -> le0101)
  b1-b4  this pod's four ports on each plane router (pod 1: eth01-04,
         pod 2: eth05-08, ...)

Plane (fabric) nodes are not in the pod template, so they are generated here:
fa0101 .. fa0416, one per config written by make_pods.py.

Run make_pods.py first so the bound config files exist.
"""

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # importing make_pods shouldn't leave __pycache__ in the repo
from make_pods import (BASE, PLANE_COUNT, PLANE_ROUTER_NUMBERS, POD_COUNT,
                       PLANE_TEMPLATE_PODS, pad, router_id)

POD_YAML_TEMPLATE = BASE / "templates" / "pod" / "pod-template.yaml"
DEFAULT_OUT = BASE / "lab" / "fabric.clab.yml"
PORTS_PER_POD = 4  # each pod uses four ports on every plane router

IMAGE = "quay.io/frrouting/frr:master"
MGMT_IPV4 = "10.99.0.0/16"    # numbering.txt: management network
MGMT_IPV6 = "3fff:99:99::/48"

POD_TOKEN = re.compile(r"tt")
PLANE_PORT = re.compile(r"ethb([1-4])")
POD_BIND = re.compile(r"(- )(pods/)")


def group(name: str) -> str:
    return (f"    {name}:\n"
            f"      kind: linux\n"
            f"      image: {IMAGE}\n"
            f'      restart-policy: "no"\n'
            f"      binds:\n"
            f"        - ../daemons.txt:/etc/frr/daemons\n"
            f"        - ../vtysh.conf:/etc/frr/vtysh.conf\n")


def split_template(text: str) -> tuple:
    """Return (node lines, link lines) from the pod template, comments dropped."""
    nodes, links, section = [], [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in ("nodes:", "links:"):
            section = stripped
            continue
        if not stripped or stripped.startswith("#"):
            continue
        if section == "nodes:":
            nodes.append(line)
        elif section == "links:":
            links.append(line)
    if not nodes or not links:
        raise ValueError(f"{POD_YAML_TEMPLATE.name}: missing nodes: or links: section")
    return nodes, links


def fill(line: str, pod: int) -> str:
    """Fill tt and ethbN for one pod; point config binds one folder up."""
    first_port = (pod - 1) * PORTS_PER_POD
    line = PLANE_PORT.sub(lambda m: f"eth{pad(first_port + int(m.group(1)))}", line)
    line = POD_TOKEN.sub(pad(pod), line)
    return POD_BIND.sub(r"\1../\2", line)


def fabric_nodes() -> list:
    lines = []
    for plane in range(1, PLANE_COUNT + 1):
        for rtr in PLANE_ROUTER_NUMBERS:
            name = router_id("fa", plane, rtr)
            lines += [f"  {name}:",
                      "    group: fabric",
                      "    binds:",
                      f"      - ../planes/plane{pad(plane)}/{name}.conf:/etc/frr/frr.conf"]
    return lines


def build(name: str, pods: int) -> str:
    node_tpl, link_tpl = split_template(POD_YAML_TEMPLATE.read_text())

    nodes, links = [], []
    for pod in range(1, pods + 1):
        nodes += [fill(line, pod) for line in node_tpl]
        links += [fill(line, pod) for line in link_tpl]
    nodes += fabric_nodes()

    indent = lambda lines: "".join(f"  {line}\n" for line in lines)
    return (f"name: {name}\n"
            f"\n"
            f"mgmt:\n"
            f"  network: {name}-mgmt\n"
            f"  ipv4-subnet: {MGMT_IPV4}\n"
            f"  ipv6-subnet: {MGMT_IPV6}\n"
            f"\n"
            f"topology:\n"
            f"  groups:\n"
            + group("leaf") + group("spine") + group("fabric") +
            f"\n"
            f"  nodes:\n"
            + indent(nodes) +
            f"\n"
            f"  links:\n"
            + indent(links))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT,
                        help="topology file (default: lab/fabric.clab.yml next to this script)")
    parser.add_argument("--name", default="autocon26",
                        help="containerlab lab name (default: autocon26)")
    parser.add_argument("-n", "--pods", type=int, default=POD_COUNT,
                        help=f"number of pods (default: {POD_COUNT})")
    args = parser.parse_args()

    if args.pods != PLANE_TEMPLATE_PODS:
        print(f"warning: plane configs have ports for {PLANE_TEMPLATE_PODS} pods; "
              f"a {args.pods}-pod topology won't match them")

    text = build(args.name, args.pods)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    nodes = len(re.findall(r"^    \w+:\n      group:", text, re.M))
    links = text.count("- endpoints:")
    print(f"{args.out}: {nodes} nodes, {links} links")


if __name__ == "__main__":
    main()

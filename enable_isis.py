#!/usr/bin/env python3
"""Enable IS-IS on the leaf-spine links of one pod in the running lab.

    ./enable_isis.py 1              # pod 1
    ./enable_isis.py 3 --dry-run    # show what would be sent to pod 3

For each router in the pod this runs one `docker exec ... vtysh` that adds,
on each leaf-spine interface (leaf eth01-16, spine eth01-16):

    interface ethNN
     ipv6 router isis labnet
     isis network point-to-point

Spine eth17-32 (the links to the plane routers) and the plane routers
themselves are not touched.

Changes go to the running config only; nothing is written to frr.conf. The
configs are bind-mounted from pods/, so `write memory` inside a router would
overwrite the generated files. Re-running make_pods.py and redeploying
returns to the IS-IS-off state.

To keep an 8-CPU host responsive, routers are configured one at a time with a
pause between them, and the script waits whenever the 1-minute load average
is above --max-load.
"""

import argparse
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True  # importing make_pods shouldn't leave __pycache__ in the repo
from make_pods import LEAF_NUMBERS, POD_COUNT, SPINE_NUMBERS, pad, router_id

ISIS_INSTANCE = "labnet"
POD_LINK_PORTS = range(1, 17)  # leaf eth01-16 -> spines, spine eth01-16 -> leaves


def vtysh_args(ports) -> list:
    """vtysh -c arguments enabling IS-IS on the given ethNN ports."""
    args = ["-c", "configure terminal"]
    for port in ports:
        args += ["-c", f"interface eth{pad(port)}",
                 "-c", f"ipv6 router isis {ISIS_INSTANCE}",
                 "-c", "isis network point-to-point",
                 "-c", "exit"]
    return args + ["-c", "end"]


def isis_ports(running_config: str) -> set:
    """ethNN interfaces that have IS-IS enabled in a running config."""
    ports = set()
    for name, body in re.findall(r"^interface (eth\d+)\n(.*?)^exit", running_config, re.M | re.S):
        if f"ipv6 router isis {ISIS_INSTANCE}" in body:
            ports.add(name)
    return ports


def pod_routers(pod: int) -> list:
    return ([router_id("le", pod, n) for n in LEAF_NUMBERS] +
            [router_id("sp", pod, n) for n in SPINE_NUMBERS])


def running_containers() -> set:
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True, check=True).stdout
    return set(out.split())


def wait_for_load(max_load: float) -> None:
    while (load := os.getloadavg()[0]) > max_load:
        print(f"  load {load:.1f} > {max_load:.1f}, waiting...", flush=True)
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pod", type=int, choices=range(1, POD_COUNT + 1), metavar="POD",
                        help=f"pod number (1-{POD_COUNT})")
    parser.add_argument("--lab", default="autocon26",
                        help="containerlab lab name (default: autocon26)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds to pause between routers (default: 1)")
    parser.add_argument("--max-load", type=float, default=(os.cpu_count() or 8) * 0.75,
                        help="wait while the 1-minute load average is above this "
                             "(default: 75%% of CPUs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands instead of running them")
    args = parser.parse_args()

    routers = pod_routers(args.pod)
    containers = {r: f"clab-{args.lab}-{r}" for r in routers}
    cmd_args = vtysh_args(POD_LINK_PORTS)
    wanted = {f"eth{pad(p)}" for p in POD_LINK_PORTS}

    if args.dry_run:
        for r in routers:
            print(" ".join(["docker", "exec", containers[r], "vtysh"] +
                           [f"'{a}'" if " " in a else a for a in cmd_args]))
        return

    missing = [c for c in containers.values() if c not in running_containers()]
    if missing:
        sys.exit(f"not running: {', '.join(missing)} (is lab '{args.lab}' deployed?)")

    failed = []
    for i, r in enumerate(routers, start=1):
        wait_for_load(args.max_load)
        result = subprocess.run(["docker", "exec", containers[r], "vtysh", *cmd_args],
                                capture_output=True, text=True)
        # vtysh prints "% Configuration applied with notes" even on success, so
        # check the running config instead of parsing its output.
        running = subprocess.run(["docker", "exec", containers[r], "vtysh",
                                  "-c", "show running-config"],
                                 capture_output=True, text=True).stdout
        missing_ports = sorted(wanted - isis_ports(running))
        ok = result.returncode == 0 and not missing_ports
        print(f"[{i:2d}/{len(routers)}] {r}: {'ok' if ok else 'FAILED'}", flush=True)
        if not ok:
            failed.append(r)
            if missing_ports:
                print(f"    IS-IS not on: {', '.join(missing_ports)}")
            for line in (result.stdout + result.stderr).splitlines():
                if "Unknown command" in line or "rror" in line:
                    print(f"    {line}")
        if i < len(routers):
            time.sleep(args.delay)

    print(f"pod {pad(args.pod)}: IS-IS enabled on {len(routers) - len(failed)}/{len(routers)} "
          f"routers ({len(POD_LINK_PORTS)} links each)")
    if failed:
        sys.exit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Enable IS-IS on one plane's downlinks (plane routers <-> spines) in the running lab.

    ./enable_plane_isis.py 1              # plane 1
    ./enable_plane_isis.py 2 --dry-run    # show what would be sent for plane 2

A plane's downlinks join its 16 routers (faPP01-faPP16, eth01-16) to the 16
spines that uplink into it: four per pod (plane 1: spines 33-36, plane 2:
37-40, ...), on spine eth17-32. Both ends need IS-IS for a link to come up,
so the script enables both:

  1. the 16 spines' eth17-32, four routers at a time (no adjacencies can form
     yet, because the plane side is still off)
  2. the 16 plane routers' eth01-16, four routers at a time; each group brings
     up its adjacencies to the spines in every pod

On each interface it adds:

    ipv6 router isis labnet
    isis network point-to-point

The four routers in a group are configured in parallel. Before each group the
script waits until the host has settled:
  - CPU busy over a --sample second window is below --max-cpu percent, and
  - the 1-minute load average is below --max-load.
The CPU check reacts within seconds; the load average lags by a minute or so,
so it mainly guards against sustained load.

Each router's running config is read back to confirm IS-IS is on every link.
Nothing is written to frr.conf (it is bind-mounted from pods/ and planes/), so
redeploying the lab returns to the IS-IS-off state. Pod-internal links are
handled by enable_isis.py.
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True  # importing shouldn't leave __pycache__ in the repo
from enable_isis import isis_ports, running_containers, vtysh_args
from make_pods import (PLANE_COUNT, PLANE_ROUTER_NUMBERS, PLANE_TEMPLATE_PODS,
                       POD_COUNT, pad, router_id, spines_for_plane)

GROUP_SIZE = 4
SPINE_UPLINK_PORTS = range(17, 33)                            # spine eth17-32 -> plane routers
PLANE_DOWNLINK_PORTS = range(1, PLANE_TEMPLATE_PODS * 4 + 1)  # plane eth01-16 -> spines


def plane_steps(plane: int) -> list:
    """(router, ports) in the order they are enabled: spines first, then plane routers."""
    spines = [router_id("sp", pod, s)
              for s in spines_for_plane(plane) for pod in range(1, POD_COUNT + 1)]
    planes = [router_id("fa", plane, r) for r in PLANE_ROUTER_NUMBERS]
    return ([(r, SPINE_UPLINK_PORTS) for r in spines] +
            [(r, PLANE_DOWNLINK_PORTS) for r in planes])


def cpu_busy(seconds: float) -> float:
    """Percent of all CPUs busy over the next `seconds`."""
    def snap():
        v = list(map(int, open("/proc/stat").readline().split()[1:]))
        return sum(v), v[3] + v[4]  # total, idle + iowait
    t0, i0 = snap()
    time.sleep(seconds)
    t1, i1 = snap()
    return 100.0 * (1 - (i1 - i0) / max(t1 - t0, 1))


def wait_until_settled(max_cpu: float, max_load: float, sample: float) -> float:
    """Block until CPU and load are under the limits; return seconds waited."""
    start = time.time()
    while True:
        cpu = cpu_busy(sample)
        load = os.getloadavg()[0]
        if cpu < max_cpu and load < max_load:
            return time.time() - start
        print(f"    waiting: cpu {cpu:.0f}% (max {max_cpu:.0f}%), "
              f"load {load:.2f} (max {max_load:.2f})", flush=True)


def enable(container: str, ports) -> list:
    """Enable IS-IS on ports; return the ethNN ports still missing it afterwards."""
    result = subprocess.run(["docker", "exec", container, "vtysh", *vtysh_args(ports)],
                            capture_output=True, text=True)
    running = subprocess.run(["docker", "exec", container, "vtysh",
                              "-c", "show running-config"],
                             capture_output=True, text=True).stdout
    wanted = {f"eth{pad(p)}" for p in ports}
    missing = sorted(wanted - isis_ports(running))
    if result.returncode != 0 and not missing:
        missing = ["(vtysh exited with an error)"]
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plane", type=int, choices=range(1, PLANE_COUNT + 1), metavar="PLANE",
                        help=f"plane number (1-{PLANE_COUNT})")
    parser.add_argument("--lab", default="autocon26",
                        help="containerlab lab name (default: autocon26)")
    parser.add_argument("--max-cpu", type=float, default=20.0,
                        help="wait while CPU busy is at or above this percent (default: 20)")
    parser.add_argument("--max-load", type=float, default=(os.cpu_count() or 8) / 2,
                        help="wait while the 1-minute load average is at or above this "
                             "(default: half the CPUs)")
    parser.add_argument("--sample", type=float, default=5.0,
                        help="seconds of CPU measurement per check (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the groups and commands instead of running them")
    args = parser.parse_args()

    steps = plane_steps(args.plane)
    groups = [steps[i:i + GROUP_SIZE] for i in range(0, len(steps), GROUP_SIZE)]
    container = lambda r: f"clab-{args.lab}-{r}"

    if args.dry_run:
        for n, group in enumerate(groups, start=1):
            print(f"group {n}/{len(groups)}: " +
                  ", ".join(f"{r} eth{pad(p[0])}-{pad(p[-1])}" for r, p in group))
            for r, ports in group:
                print("  docker exec", container(r), "vtysh",
                      " ".join(f"'{a}'" if " " in a else a for a in vtysh_args(ports)))
        return

    missing = [container(r) for r, _ in steps if container(r) not in running_containers()]
    if missing:
        sys.exit(f"not running: {', '.join(missing)} (is lab '{args.lab}' deployed?)")

    failed = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=GROUP_SIZE) as pool:
        for n, group in enumerate(groups, start=1):
            waited = wait_until_settled(args.max_cpu, args.max_load, args.sample)
            names = ", ".join(r for r, _ in group)
            print(f"[group {n}/{len(groups)}] {names} (waited {waited:.0f}s)", flush=True)
            results = pool.map(lambda step: (step[0], enable(container(step[0]), step[1])), group)
            for r, missing_ports in results:
                if missing_ports:
                    failed.append(r)
                    print(f"    {r}: FAILED, IS-IS not on: {', '.join(missing_ports)}")
                else:
                    print(f"    {r}: ok")

    total = len(steps)
    print(f"plane {pad(args.plane)}: IS-IS enabled on {total - len(failed)}/{total} routers "
          f"in {time.time() - started:.0f}s")
    if failed:
        sys.exit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()

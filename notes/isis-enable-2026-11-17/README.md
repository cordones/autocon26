# IS-IS enable run, 17–18 Nov 2026

Rehearsal of turning on IS-IS across the running 192-router lab (4 pods,
4 planes) step by step, with host CPU and load recorded on an 8-CPU host.

Order: `./enable_isis.py 1` … `4` (pod leaf–spine links), then
`./enable_plane_isis.py 1` … `4` (spine–plane links). All IS-IS changes were
made by those scripts, in the running config only; redeploying the lab
returns to IS-IS off on all links.

## Result

Every run reported all 32 routers ok, and the fabric came up as expected:

| After | Routes per router | Notes |
|---|---|---|
| each pod | 31 | 16 neighbours per leaf/spine, 16-way ECMP leaf to leaf |
| plane 1 | 143 | 4-way ECMP le0101 to le0416 |
| plane 2 | 159 | 8-way ECMP |
| plane 3 | 175 | 12-way ECMP |
| plane 4 | 191 | 16-way ECMP; all 192 loopbacks reachable (spot-checked) |

## Host load

| Run | Time | Peak CPU | Peak 1-min load | Samples with load ≥ 6 |
|---|---|---|---|---|
| pod 1 | 74 s | 55% | 2.1 | – |
| pod 2 | 76 s | 57% | 2.1 | – |
| pod 3 | 76 s | 57% | 1.3 | – |
| pod 4 | ~75 s | 56% | ~2.6 | – |
| plane 1 | 189 s | 60% | 17.0 | 16 of 59 |
| plane 2 | 148 s | 58% | 16.4 | 13 of 50 |
| plane 3 | 254 s | 59% | 30.1 | 52 of 72 |
| plane 4 | 431 s | 64% | 38.8 | 75 of 108 |

CPU never reached the 75% warning level. The pressure shows up as the load
average: short bursts with many processes runnable at once (289 at one point)
while total CPU stays modest.

## Findings

- **Start-of-run burst (pods).** Every pod run began with about 16–18 s of
  ~55% CPU, from `dockerd` and `containerd` (~2 cores each), before any
  adjacency could form (`top-pod3-first-24s.txt`). The scripts' own Docker
  calls don't account for it (listing containers 0.5 s; five `docker exec`
  calls < 0.2 CPU-seconds), and Docker stayed idle for 2.5 min with nothing
  running. Cause not found.
- **Plane bursts grow with each plane.** Each group of plane routers coming
  up spiked the load: one spike of ~16–17 on planes 1–2, several of 21–30 on
  plane 3, up to 38.8 on plane 4. The script's settle check (CPU < 20% and
  load < 4) delayed groups by up to 250 s.
- **Bursts continue after the last plane.** With nothing running, the load
  still jumped to ~17–26 every minute or two (`idle-after-plane4.txt`), then
  died down to ~2.7 within about 10 minutes. Adjacencies were stable (one
  flap each, from coming up). In 100 s, 38 of 191 LSPs went up exactly one
  sequence number with unchanged size (`lsp-seq-changes-100s.txt`), which
  looks like periodic LSP refresh, synchronised because routers were enabled
  in batches. Likely, not proven.
- **Checking adds load.** A full read-only check (one `docker exec` per
  router) pushed the load up noticeably; spot-checking a few routers is
  gentler.

## Files

- `load-pod*.csv`, `load-plane*.csv` – host CPU % and load average
  (2 s samples for pods 1–3, 10 s for pod 4, 5 s with warnings for planes).
  `phase` is baseline / enabling / after.
- `enable-pod*.log`, `enable-plane*.log` – script output, including every
  settle-check wait.
- `top-pod3-first-24s.txt` – busiest processes during the pod 3 start burst.
- `idle-after-plane4.txt` – 3 min of CPU, load and runnable processes after
  plane 4, with no commands sent to the routers.
- `lsp-seq-changes-100s.txt` – le0101's LSP database entries whose sequence
  number changed over 100 s (LSP, old seq, size, new seq, size).
- `tools/sampler.py`, `tools/monitor.py` – the samplers used
  (`python3 monitor.py OUT.csv PHASE_FILE`; monitor adds warnings at
  CPU ≥ 75% or load ≥ 75% of CPUs).

**Caveat:** `load-pod4.csv` has interleaved rows. A sampler left over from a
failed first attempt wrote to the same file; the overall pattern holds but
individual rows are unreliable.

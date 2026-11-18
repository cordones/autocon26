import sys, time, os
out = open(sys.argv[1], "w", buffering=1); phasef = sys.argv[2]
ncpu = os.cpu_count() or 8; CPU_WARN = 75.0; LOAD_WARN = 0.75 * ncpu
out.write("t,phase,cpu_pct,load1,warn\n")
def snap():
    v = list(map(int, open("/proc/stat").readline().split()[1:])); return sum(v), v[3] + v[4]
t0 = time.time(); prev = snap()
while True:
    time.sleep(5)
    cur = snap(); tot, idle = cur[0]-prev[0], cur[1]-prev[1]; prev = cur
    cpu = 100*(tot-idle)/max(tot,1); l1 = os.getloadavg()[0]
    phase = open(phasef).read().strip()
    w = []
    if cpu >= CPU_WARN: w.append(f"CPU {cpu:.0f}% >= {CPU_WARN:.0f}%")
    if l1 >= LOAD_WARN: w.append(f"load {l1:.2f} >= {LOAD_WARN:.1f}")
    out.write(f"{time.time()-t0:.0f},{phase},{cpu:.1f},{l1:.2f},{'; '.join(w)}\n")

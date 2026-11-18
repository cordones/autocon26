import sys, time, os
out = open(sys.argv[1], "w", buffering=1)
out.write("t,phase,cpu_pct,load1,load5,load15\n")
def cpu():
    f = open("/proc/stat").readline().split()[1:]
    v = list(map(int, f)); idle = v[3] + v[4]
    return sum(v), idle
t0 = time.time(); prev = cpu()
while True:
    time.sleep(2)
    cur = cpu(); tot, idle = cur[0]-prev[0], cur[1]-prev[1]; prev = cur
    phase = open(sys.argv[2]).read().strip() if os.path.exists(sys.argv[2]) else "?"
    l = os.getloadavg()
    out.write(f"{time.time()-t0:.0f},{phase},{100*(tot-idle)/tot:.1f},{l[0]:.2f},{l[1]:.2f},{l[2]:.2f}\n")

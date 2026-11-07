import os, subprocess, threading, time, glob, itertools, sys, collections
imgs = sorted(glob.glob(sys.argv[1] + "/*.png")); it = itertools.cycle(imgs); lock = threading.Lock()
stages = [(2, 75), (6, 75), (12, 75), (24, 90)]
codes = collections.Counter(); stop_at = [0]
def worker():
    while time.time() < stop_at[0]:
        with lock: f = next(it)
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "150", "-w", "%{http_code}", "-F", f"file=@{f};type=image/png",
                              os.environ.get("OCR_LAB_URL", "http://localhost") + "/api/extract"], capture_output=True, text=True).stdout
        with lock: codes[out] += 1
start = time.time(); print("start", int(start), flush=True); threads = []
for n, dur in stages:
    stop_at[0] = start + sum(d for _, d in stages[: stages.index((n, dur)) + 1])
    while len(threads) < n:
        t = threading.Thread(target=worker, daemon=True); t.start(); threads.append(t)
    print(f"stage {n} users until +{int(stop_at[0]-start)}s", flush=True)
    time.sleep(max(0, stop_at[0] - time.time()))
for t in threads: t.join(timeout=160)
print("end", int(time.time()), dict(codes), flush=True)

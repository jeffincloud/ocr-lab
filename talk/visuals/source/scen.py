import subprocess, threading, time, glob, itertools, sys, collections, json
imgs = sorted(glob.glob(sys.argv[1] + "/*.png")); it = itertools.cycle(imgs); lock = threading.Lock()
def run(n, dur):
    codes = collections.Counter(); lat = []; stop = time.time() + dur
    def w():
        while time.time() < stop:
            with lock: f = next(it)
            t = time.time()
            c = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "150", "-w", "%{http_code}", "-F", f"file=@{f};type=image/png",
                                "http://localhost/api/extract"], capture_output=True, text=True).stdout
            with lock: codes[c] += 1; lat.append((c, time.time() - t))
    ts = [threading.Thread(target=w) for _ in range(n)]; start = time.time()
    [t.start() for t in ts]; [t.join() for t in ts]
    ok = sorted(l for c, l in lat if c == "200")
    return dict(users=n, start=int(start), end=int(time.time()), codes=dict(codes),
                p50=ok[len(ok) // 2] if ok else None, p95=ok[int(len(ok) * .95) - 1] if ok else None, n_ok=len(ok))
a = run(1, 90); time.sleep(20); b = run(24, 150)
json.dump([a, b], open(sys.argv[2], "w")); print(json.dumps([a, b], indent=1))

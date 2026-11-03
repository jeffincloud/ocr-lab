"""Send every passport in a folder once, N at a time, and keep each response.  python3 batch.py DIR N OUT.json"""
import concurrent.futures as cf, glob, json, subprocess, sys, time
d, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
files = sorted(glob.glob(d + "/*.png"))
def one(f):
    t = time.time()
    r = subprocess.run(["curl", "-s", "-m", "180", "-w", "\n%{http_code}", "-F", f"file=@{f};type=image/png",
                        "http://localhost/api/extract"], capture_output=True, text=True).stdout
    body, code = r.rsplit("\n", 1)
    try: body = json.loads(body)
    except Exception: pass
    return dict(file=f.split("/")[-1], code=code, latency=time.time() - t, start=t, body=body)
start = time.time()
with cf.ThreadPoolExecutor(n) as ex: res = list(ex.map(one, files))
json.dump(dict(start=int(start), end=int(time.time()), results=res), open(out, "w"), indent=1)
ok = [r for r in res if r["code"] == "200"]
print(f"{len(ok)}/{len(res)} ok in {time.time()-start:.0f}s; codes", {c: sum(r['code'] == c for r in res) for c in set(r['code'] for r in res)})

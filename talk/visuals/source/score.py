import json, sys, statistics as st, collections
truth = {json.loads(l)["file"]: json.loads(l)["truth"] for l in open(sys.argv[1])}
FIELDS = ["surname", "given_names", "passport_number", "nationality", "date_of_birth", "sex", "date_of_issue", "date_of_expiry"]
norm = lambda v: " ".join(str(v or "").upper().replace("<", " ").split())
out = {}
for name in sys.argv[2:]:
    d = json.load(open(name)); res = d["results"]; ok = [r for r in res if r["code"] == "200"]
    errs = collections.Counter(); ex = []
    for r in ok:
        f, t = r["body"]["fields"], truth[r["file"]]
        for k in FIELDS:
            if norm(f.get(k)) != norm(t[k]):
                errs[k] += 1; ex.append((r["file"], k, f.get(k), t[k]))
    lat = sorted(r["latency"] for r in ok)
    out_tok = [r["body"]["usage"]["output_tokens"] for r in ok]
    in_tok = [r["body"]["usage"]["input_tokens"] for r in ok]
    mrz = collections.Counter(r["body"].get("mrz_result") for r in ok)
    fails = [(r["file"], r["code"], str(r["body"])[:90]) for r in res if r["code"] != "200"]
    out[name] = dict(start=d["start"], end=d["end"], n=len(res), ok=len(ok), field_errors=sum(errs.values()), fields_checked=len(ok) * len(FIELDS),
                     errors_by_field=dict(errs), p50=lat[len(lat) // 2], p95=lat[max(0, int(len(lat) * .95) - 1)], wall=d["end"] - d["start"],
                     out_tokens_mean=st.mean(out_tok), out_tokens_max=max(out_tok), in_tokens_mean=st.mean(in_tok), mrz=dict(mrz), failures=fails, examples=ex[:12])
    print("==", name.split("/")[-1], json.dumps({k: v for k, v in out[name].items() if k != "examples"}, default=str)[:900])
    for e in ex[:12]: print("   wrong:", e)
json.dump(out, open(sys.argv[1].rsplit("/", 2)[0] + "/think_scores.json", "w"), indent=1, default=str)

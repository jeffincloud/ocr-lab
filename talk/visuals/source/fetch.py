"""Pull the chart series for layers.py from the lab's Prometheus.  python3 fetch.py START END out.json"""
import json
import subprocess
import sys
import urllib.parse

start, end = int(sys.argv[1]), int(sys.argv[2])
P = "/api/v1/namespaces/monitoring/services/kps-prometheus:9090/proxy/api/v1/query_range?"


def series(q):
    url = P + urllib.parse.urlencode({"query": q, "start": start, "end": end, "step": 15})
    r = json.loads(subprocess.run(["kubectl", "get", "--raw", url], capture_output=True, text=True, check=True).stdout)
    res = r["data"]["result"]
    if not res:
        return []
    pts = []
    for t, v in res[0]["values"]:
        v = float(v)
        pts.append((float(t) - start, None if v != v else v))
    return pts


q50 = "histogram_quantile(0.5, sum by (le) (rate({m}[1m])))"
charts = [
    dict(title="Request latency, p50", unit=" s", series=[
        dict(name="end to end", color="#0086FF", points=series(q50.format(m='ocr_extract_duration_seconds_bucket{outcome="ok"}'))),
        dict(name="first content", color="#ED561B", points=series(q50.format(m="ocr_upstream_time_to_first_token_seconds_bucket"))),
        dict(name="engine first token", color="#93EAFF", points=series(q50.format(m="vllm:time_to_first_token_seconds_bucket"))),
    ]),
    dict(title="Generated tokens per second", series=[
        dict(name="vLLM", color="#50B432", fill=True, points=series("sum(rate(vllm:generation_tokens_total[1m]))")),
    ]),
    dict(title="GPU: utilization vs power", unit="%", ymax=100, series=[
        dict(name="utilization", color="#ED561B", points=series("max(DCGM_FI_DEV_GPU_UTIL)")),
        dict(name="power, % of 350 W", color="#0086FF", fill=True, points=series("max(DCGM_FI_DEV_POWER_USAGE) / 350 * 100")),
    ]),
    dict(title="Running vs waiting requests", series=[
        dict(name="running", color="#0086FF", fill=True, points=series("sum(vllm:num_requests_running)")),
        dict(name="waiting", color="#ED561B", points=series("sum(vllm:num_requests_waiting)")),
    ]),
]
json.dump({"charts": charts, "footer": ""}, open(sys.argv[3], "w"))
for c in charts:
    for s in c["series"]:
        vals = [v for _, v in s["points"] if v is not None]
        print(c["title"], "|", s["name"], len(vals), "pts", "min", round(min(vals), 2) if vals else None, "max", round(max(vals), 2) if vals else None)

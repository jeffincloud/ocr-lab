// Many simulated users uploading synthetic passports to the OCR app.
//
// Every request uses a different generated passport (tools/passport-gen), and
// every response is scored against that passport's ground truth. So besides
// latency and errors, this script measures what the user actually cares
// about: did the extraction come back right?
//
//   k6 run -e BASE_URL=http://<host>/api -e SCENARIO=users -e PEAK_USERS=100 loadtest/k6/ocr-users.js
//
// Scenarios (SCENARIO=...):
//   smoke   1 user for 1 minute. Sanity check before anything bigger.
//   users   Closed model: ramp to PEAK_USERS users, each waiting 1-5 s between
//           uploads (people reading results). "Many users at once".
//   rate    Open model: arrival rate climbs in steps up to MAX_RPS. Finds the
//           knee where queue time and latency take off. Use for capacity.
//   spike   Arrival rate jumps from 1 to SPIKE_RPS in 10 s, holds, drops.
//   soak    Constant SOAK_RPS for SOAK_MINUTES (thermal throttling, leaks, burn rate).
//
// Results go to Prometheus with:
//   K6_PROMETHEUS_RW_SERVER_URL=http://<prometheus>/api/v1/write \
//   K6_PROMETHEUS_RW_TREND_STATS="p(50),p(95),p(99)" \
//   k6 run -o experimental-prometheus-rw --tag run_id=$RUN_ID ...
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';
import { open as fsOpen, SeekMode } from 'k6/experimental/fs';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const EXTRACT_PATH = __ENV.EXTRACT_PATH || '/extract';
const DATA_DIR = __ENV.DATA_DIR || 'loadtest/data/passports';
const SCENARIO = __ENV.SCENARIO || 'smoke';
const PEAK_USERS = parseInt(__ENV.PEAK_USERS || '50');
const MAX_RPS = parseInt(__ENV.MAX_RPS || '20');
const SPIKE_RPS = parseInt(__ENV.SPIKE_RPS || '30');
const SOAK_RPS = parseFloat(__ENV.SOAK_RPS || '5');
const SOAK_MINUTES = parseInt(__ENV.SOAK_MINUTES || '60');
// Log the trace ID of any request slower than this, to jump straight to Tempo.
const SLOW_MS = parseInt(__ENV.SLOW_MS || '8000');

const FIELDS = ['surname', 'given_names', 'passport_number', 'nationality', 'date_of_birth', 'sex',
  'date_of_issue', 'date_of_expiry', 'issuing_authority'];

const manifest = new SharedArray('manifest', () =>
  open(`${DATA_DIR}/manifest.jsonl`).split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l)));

// k6/experimental/fs shares file contents across VUs instead of copying every
// image into every VU's memory, which matters at hundreds of users.
const files = {};
for (const rec of manifest) {
  files[rec.file] = await fsOpen(`${DATA_DIR}/${rec.file}`);
}

const fieldCorrect = new Rate('ocr_field_correct');       // per field, all requests
const exactMatch = new Rate('ocr_exact_match');           // all fields right
const mrzValid = new Rate('ocr_mrz_valid');               // API says check digits pass
const inputTokens = new Trend('ocr_input_tokens');
const outputTokens = new Trend('ocr_output_tokens');
const statusCount = new Counter('ocr_status');

const SCENARIOS = {
  smoke: { executor: 'constant-vus', vus: 1, duration: '1m' },
  users: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: Math.ceil(PEAK_USERS / 4) },
      { duration: '3m', target: Math.ceil(PEAK_USERS / 2) },
      { duration: '3m', target: PEAK_USERS },
      { duration: '5m', target: PEAK_USERS },
      { duration: '2m', target: 0 },
    ],
    gracefulRampDown: '60s',
  },
  rate: {
    executor: 'ramping-arrival-rate',
    startRate: 1,
    timeUnit: '1s',
    preAllocatedVUs: 50,
    maxVUs: MAX_RPS * 30,
    stages: Array.from({ length: 6 }, (_, i) => [
      { duration: '30s', target: Math.max(1, Math.round((MAX_RPS * (i + 1)) / 6)) },
      { duration: '2m', target: Math.max(1, Math.round((MAX_RPS * (i + 1)) / 6)) },
    ]).flat(),
  },
  spike: {
    executor: 'ramping-arrival-rate',
    startRate: 1,
    timeUnit: '1s',
    preAllocatedVUs: 50,
    maxVUs: SPIKE_RPS * 30,
    stages: [
      { duration: '2m', target: 1 },
      { duration: '10s', target: SPIKE_RPS },
      { duration: '3m', target: SPIKE_RPS },
      { duration: '10s', target: 1 },
      { duration: '3m', target: 1 },
    ],
  },
  soak: {
    executor: 'constant-arrival-rate',
    rate: Math.round(SOAK_RPS * 10),
    timeUnit: '10s',
    duration: `${SOAK_MINUTES}m`,
    preAllocatedVUs: 50,
    maxVUs: 500,
  },
};

// Thresholds mirror the SLOs in observability/slo/ so a run "passes" exactly
// when it would have kept the SLOs. They report; they don't abort the run.
export const options = {
  scenarios: { [SCENARIO]: SCENARIOS[SCENARIO] },
  thresholds: {
    'http_req_failed': ['rate<0.005'],
    'http_req_duration{expected_response:true}': ['p(95)<8000'],
    'ocr_mrz_valid': ['rate>0.98'],
    'ocr_field_correct': ['rate>0.97'],
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(90)', 'p(95)', 'p(99)', 'max'],
  tags: { scenario_name: SCENARIO },
};

function hex(bytes) {
  let s = '';
  for (let i = 0; i < bytes; i++) s += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
  return s;
}

function norm(v) {
  return String(v ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

async function readImage(name) {
  const f = files[name];
  const info = await f.stat();
  const buf = new Uint8Array(info.size);
  await f.seek(0, SeekMode.Start);
  let off = 0;
  while (off < info.size) {
    const n = await f.read(buf.subarray(off));
    if (n === null) break;
    off += n;
  }
  return buf.buffer;
}

export default async function () {
  const rec = manifest[Math.floor(Math.random() * manifest.length)];
  const body = await readImage(rec.file);
  // Start the trace here so Tempo shows the client's view as the root.
  const traceId = hex(16);
  const res = http.post(`${BASE_URL}${EXTRACT_PATH}`, { file: http.file(body, rec.file, 'image/png') }, {
    headers: { traceparent: `00-${traceId}-${hex(8)}-01` },
    timeout: '180s',
    tags: { name: 'extract' },
  });
  statusCount.add(1, { status: String(res.status) });

  const ok = check(res, { 'status 200': (r) => r.status === 200 });
  if (res.timings.duration > SLOW_MS || !ok) {
    console.warn(`slow_or_failed status=${res.status} ms=${Math.round(res.timings.duration)} trace_id=${traceId}`);
  }
  if (ok) {
    const data = res.json();
    let all = true;
    for (const f of FIELDS) {
      const good = norm(data.fields[f]) === norm(rec.truth[f]);
      fieldCorrect.add(good, { field: f });
      all = all && good;
    }
    exactMatch.add(all);
    mrzValid.add(data.mrz_result === 'valid');
    if (data.usage?.input_tokens) inputTokens.add(data.usage.input_tokens);
    if (data.usage?.output_tokens) outputTokens.add(data.usage.output_tokens);
  }

  if (SCENARIO === 'users' || SCENARIO === 'smoke') {
    sleep(1 + Math.random() * 4); // think time; arrival-rate scenarios pace themselves
  }
}

export function handleSummary(data) {
  const runId = exec.test.options.tags?.run_id || 'local';
  return {
    stdout: textSummary(data),
    [`loadtest/results/${runId}-${SCENARIO}.json`]: JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const m = data.metrics;
  const v = (name, stat) => (m[name] && m[name].values[stat] !== undefined ? m[name].values[stat] : NaN);
  const lines = [
    `scenario=${SCENARIO} requests=${v('http_reqs', 'count')} rps=${v('http_reqs', 'rate').toFixed(2)}`,
    `latency p50=${v('http_req_duration', 'p(50)').toFixed(0)}ms p95=${v('http_req_duration', 'p(95)').toFixed(0)}ms p99=${v('http_req_duration', 'p(99)').toFixed(0)}ms`,
    `errors=${(v('http_req_failed', 'rate') * 100).toFixed(2)}%`,
    `field_correct=${(v('ocr_field_correct', 'rate') * 100).toFixed(2)}% exact_match=${(v('ocr_exact_match', 'rate') * 100).toFixed(2)}% mrz_valid=${(v('ocr_mrz_valid', 'rate') * 100).toFixed(2)}%`,
  ];
  for (const [name, t] of Object.entries(data.metrics)) {
    if (t.thresholds) {
      for (const [expr, res] of Object.entries(t.thresholds)) {
        lines.push(`threshold ${name} ${expr}: ${res.ok ? 'PASS' : 'FAIL'}`);
      }
    }
  }
  return lines.join('\n') + '\n';
}

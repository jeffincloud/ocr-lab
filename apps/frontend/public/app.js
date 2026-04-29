// API base:
//   - default "/api" → uses nginx reverse proxy in the cluster / docker build
//   - override via ?apiBase=http://localhost:8080 (stored in localStorage) for local dev
const params = new URLSearchParams(window.location.search);
if (params.has("apiBase")) {
  localStorage.setItem("apiBase", params.get("apiBase"));
}
const API_BASE = localStorage.getItem("apiBase") || "/api";

const $ = (id) => document.getElementById(id);
const dropzone = $("dropzone");
const fileInput = $("fileInput");
const dropzoneEmpty = $("dropzoneEmpty");
const preview = $("preview");
const extractBtn = $("extractBtn");
const resetBtn = $("resetBtn");
const results = $("results");
const spinner = $("spinner");
const errorEl = $("error");
const output = $("output");
const fieldsCard = $("fieldsCard");
const rawJson = $("rawJson");
const apiBadge = $("apiBadge");

apiBadge.textContent = `API: ${API_BASE}`;

let currentFile = null;

["dragover", "dragenter"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  }),
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  }),
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
fileInput.addEventListener("change", (e) => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

function handleFile(file) {
  if (!file.type.startsWith("image/")) {
    showError(`Unsupported file type: ${file.type || "unknown"}`);
    return;
  }
  currentFile = file;
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  dropzoneEmpty.hidden = true;
  extractBtn.disabled = false;
  resetBtn.hidden = false;
  results.hidden = true;
}

resetBtn.addEventListener("click", () => {
  currentFile = null;
  fileInput.value = "";
  preview.hidden = true;
  preview.src = "";
  dropzoneEmpty.hidden = false;
  extractBtn.disabled = true;
  resetBtn.hidden = true;
  results.hidden = true;
});

extractBtn.addEventListener("click", async () => {
  if (!currentFile) return;
  results.hidden = false;
  spinner.hidden = false;
  errorEl.hidden = true;
  output.hidden = true;
  extractBtn.disabled = true;
  try {
    const fd = new FormData();
    fd.append("file", currentFile);
    const res = await fetch(`${API_BASE}/extract`, { method: "POST", body: fd });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`HTTP ${res.status} — ${body.slice(0, 200)}`);
    }
    const data = await res.json();
    renderFields(data.fields);
    rawJson.textContent = JSON.stringify(data, null, 2);
    output.hidden = false;
  } catch (err) {
    showError(err.message);
  } finally {
    spinner.hidden = true;
    extractBtn.disabled = false;
  }
});

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.hidden = false;
  results.hidden = false;
  output.hidden = true;
}

const LABELS = {
  surname: "Surname",
  given_names: "Given names",
  passport_number: "Passport number",
  nationality: "Nationality",
  date_of_birth: "Date of birth",
  sex: "Sex",
  date_of_issue: "Date of issue",
  date_of_expiry: "Date of expiry",
  issuing_authority: "Issuing authority",
};

function renderFields(f) {
  const cards = Object.entries(LABELS)
    .map(([key, label]) => {
      const val = f[key];
      const empty = val == null || val === "";
      return `
        <div class="field">
          <div class="field-label">${label}</div>
          <div class="field-value${empty ? " empty" : ""}">${empty ? "—" : escapeHtml(String(val))}</div>
        </div>`;
    })
    .join("");
  const mrz = `
    <div class="field field-mrz">
      <div class="field-label">MRZ</div>
      <pre class="field-value">${escapeHtml(f.mrz_line1 || "")}\n${escapeHtml(f.mrz_line2 || "")}</pre>
    </div>`;
  fieldsCard.innerHTML = cards + mrz;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

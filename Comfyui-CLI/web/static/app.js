const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let pollTimer = null;
let currentJobId = null;
let config = null;

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function setStatus(healthy, text) {
  const dot = $("#statusDot");
  const el = $("#statusText");
  dot.className = "status-dot " + (healthy ? "ok" : healthy === false ? "err" : "warn");
  el.textContent = text;
}

async function checkHealth() {
  try {
    const data = await api("/api/health");
    const wfTotal = data.workflows_count ?? (data.workflows || []).length;
    const wfReady = data.workflows
      ? (data.workflows || []).filter((w) => w.ready).length
      : null;
    setStatus(
      data.healthy,
      data.healthy
        ? wfReady !== null
          ? `ComfyUI 在线 · ${wfReady}/${wfTotal} 工作流就绪`
          : `ComfyUI 在线 · ${wfTotal} 个工作流`
        : `ComfyUI 离线 (${data.endpoint})`
    );
  } catch {
    setStatus(false, "无法连接服务，请运行 ./start-web.sh");
  }
}

function fillProfiles(selects) {
  if (!config?.profiles) return;
  const names = Object.keys(config.profiles);
  selects.forEach((sel) => {
    sel.innerHTML = names
      .map(
        (n) =>
          `<option value="${n}"${n === config.default_profile ? " selected" : ""}>${n}</option>`
      )
      .join("");
  });
}

function fillWorkflows() {
  api("/api/workflows")
    .then((data) => {
      const imageWf = (data.workflows || []).filter((w) => w.category === "image");
      const videoWf = (data.workflows || []).filter((w) => w.category === "video");

      const fill = (sel, list) => {
        sel.innerHTML =
          '<option value="">默认</option>' +
          list.map((w) => `<option value="${w.name}">${w.display_name || w.name}</option>`).join("");
      };
      fill($("#workflowT2i"), imageWf);
      fill($("#workflowT2v"), videoWf);

      const list = $("#workflowList");
      if (!data.workflows?.length) {
        list.innerHTML = '<p class="muted">暂无工作流</p>';
        return;
      }
      list.innerHTML = data.workflows
        .map(
          (w) => `
        <div class="workflow-card">
          <h4>${w.display_name || w.name}</h4>
          <div class="meta">
            <span class="badge ${w.ready ? "ok" : "err"}">${w.ready ? "就绪" : "未就绪"}</span>
            <span>${w.category || ""} · ${w.source || "local"}</span>
          </div>
          ${w.description ? `<p class="meta" style="margin-top:0.35rem">${w.description}</p>` : ""}
        </div>`
        )
        .join("");
    })
    .catch(() => {
      $("#workflowList").innerHTML = '<p class="muted">加载失败</p>';
    });
}

function showJobStatus(job) {
  const el = $("#jobStatus");
  el.className = "job-status " + (job.status || "");
  const labels = { pending: "排队中", running: "生成中", completed: "已完成", failed: "失败" };
  let html = "";
  if (job.status === "pending" || job.status === "running") {
    html = `<span class="spinner"></span>`;
  }
  html += `${labels[job.status] || job.status}`;
  if (job.meta?.prompt) html += ` · ${job.meta.prompt}`;
  if (job.error) html += `<br><span style="color:var(--error)">${job.error}</span>`;
  if (job.result?.duration_sec) html += `<br>耗时 ${job.result.duration_sec}s`;
  el.innerHTML = html;
}

function showResult(job) {
  const area = $("#resultArea");
  if (job.status !== "completed" || !job.result?.output_urls?.length) {
    if (job.status === "failed") area.innerHTML = "";
    return;
  }
  const urls = job.result.output_urls;
  const isImageJob = job.kind === "t2i";
  const displayUrls = isImageJob && urls.length > 1 ? [urls[urls.length - 1]] : urls;

  const html = displayUrls
    .map((url) => {
      const isVideo = /\.(mp4|webm|gif)$/i.test(url);
      if (isVideo) return `<video src="${url}" controls autoplay loop></video>`;
      return `<img src="${url}" alt="output" />`;
    })
    .join("");

  const extra =
    isImageJob && urls.length > 1
      ? `<p class="result-meta">共 ${urls.length} 张，已显示最后一张</p>`
      : "";

  area.innerHTML =
    html +
    extra +
    `<div class="result-meta">${displayUrls.map((u) => `<a href="${u}" target="_blank" style="color:var(--accent)">${u}</a>`).join("<br>")}</div>`;
}

async function refreshJobHistory() {
  try {
    const data = await api("/api/jobs");
    const ul = $("#jobHistory");
    const jobs = data.jobs || [];
    if (!jobs.length) {
      ul.innerHTML = '<li class="muted">无记录</li>';
      return;
    }
    ul.innerHTML = jobs
      .map(
        (j) =>
          `<li data-id="${j.id}">${j.kind} · ${j.status} · ${j.meta?.prompt || j.id.slice(0, 8)}</li>`
      )
      .join("");
    ul.querySelectorAll("li[data-id]").forEach((li) => {
      li.addEventListener("click", () => loadJob(li.dataset.id));
    });
  } catch {
    /* ignore */
  }
}

async function loadJob(jobId) {
  const job = await api(`/api/jobs/${jobId}`);
  currentJobId = jobId;
  showJobStatus(job);
  showResult(job);
}

function startPolling(jobId) {
  currentJobId = jobId;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      showJobStatus(job);
      if (job.status === "completed") {
        showResult(job);
        clearInterval(pollTimer);
        pollTimer = null;
        refreshJobHistory();
        enableForms(true);
      } else if (job.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        refreshJobHistory();
        enableForms(true);
      }
    } catch {
      clearInterval(pollTimer);
      enableForms(true);
    }
  }, 2000);
}

function enableForms(enabled) {
  $$(".btn.primary").forEach((b) => (b.disabled = !enabled));
}

async function submitJob(endpoint, body) {
  enableForms(false);
  $("#resultArea").innerHTML = "";
  showJobStatus({ status: "pending", meta: body.prompt ? { prompt: body.prompt.slice(0, 80) } : {} });
  try {
    const data = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    startPolling(data.job_id);
  } catch (err) {
    showJobStatus({ status: "failed", error: err.message });
    enableForms(true);
  }
}

// Tabs
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $("#panel-" + tab.dataset.tab).classList.add("active");
  });
});

// Forms
$("#formT2i").addEventListener("submit", (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  submitJob("/api/image/t2i", {
    prompt: fd.get("prompt"),
    negative_prompt: fd.get("negative_prompt") || "",
    profile: fd.get("profile") || null,
    workflow: fd.get("workflow") || null,
  });
});

$("#formT2v").addEventListener("submit", (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const length = fd.get("length");
  submitJob("/api/video/t2v", {
    prompt: fd.get("prompt"),
    negative_prompt: fd.get("negative_prompt") || "",
    profile: fd.get("profile") || null,
    workflow: fd.get("workflow") || null,
    length: length ? parseInt(length, 10) : null,
  });
});

$("#formI2v").addEventListener("submit", async (e) => {
  e.preventDefault();
  enableForms(false);
  $("#resultArea").innerHTML = "";
  const fd = new FormData(e.target);
  showJobStatus({ status: "pending", meta: { prompt: String(fd.get("prompt")).slice(0, 80) } });
  try {
    const data = await api("/api/video/i2v", { method: "POST", body: fd });
    startPolling(data.job_id);
  } catch (err) {
    showJobStatus({ status: "failed", error: err.message });
    enableForms(true);
  }
});

$('input[name="image"]')?.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  const preview = $("#i2vPreview");
  if (!file) {
    preview.innerHTML = "";
    return;
  }
  const url = URL.createObjectURL(file);
  preview.innerHTML = `<img src="${url}" alt="preview" />`;
});

// Init
(async () => {
  try {
    config = await api("/api/config");
    fillProfiles([$("#profileT2i"), $("#profileT2v"), $("#profileI2v")]);
  } catch {
    /* config optional */
  }
  checkHealth();
  fillWorkflows();
  refreshJobHistory();
  setInterval(checkHealth, 30000);
})();
